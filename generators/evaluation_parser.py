"""
评估报告解析器
从Markdown格式的评估报告中提取结构化数据
用于构建DSPy优化器的训练集
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict


@dataclass
class DimensionScore:
    """维度评分"""
    name: str
    score: float
    max_score: float
    rating: str
    weight: str


@dataclass
class Problem:
    """发现的问题"""
    description: str
    severity: str  # "严重" 或 "一般"
    location: str
    evidence: str


@dataclass
class EvaluationReport:
    """完整的评估报告"""
    report_id: str
    project_name: str
    generated_at: str
    total_score: float
    rating: str
    dimensions: List[DimensionScore]
    problems: List[Problem]
    raw_content: str = ""
    length_budget: Optional[int] = None


class EvaluationParser:
    """评估报告解析器"""
    
    # 维度名称映射（中英文）
    DIMENSION_MAP = {
        "目标达成度": "goal_achievement",
        "流程遵循度": "process_compliance", 
        "交互体验性": "interaction_experience",
        "幻觉与边界": "hallucination_boundary",
        "教学策略": "teaching_strategy"
    }
    
    def __init__(self):
        pass
    
    def parse_file(self, file_path: str) -> Optional[EvaluationReport]:
        """解析单个评估报告文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.parse_content(content, file_path)
        except Exception as e:
            print(f"解析文件失败 {file_path}: {e}")
            return None
    
    def parse_content(self, content: str, file_path: str = "") -> EvaluationReport:
        """解析报告内容"""
        # 提取报告ID（从文件名）
        report_id = Path(file_path).stem if file_path else "unknown"
        
        # 提取项目名（从路径或内容）
        project_name = self._extract_project_name(file_path, content)
        
        # 提取生成时间
        generated_at = self._extract_datetime(content)
        
        # 提取总分
        total_score = self._extract_total_score(content)
        
        # 提取评级
        rating = self._extract_rating(content)
        # 尝试提取长度预算（可选）
        lb = None
        lb_match = re.search(r'(?:长度预算|字数预算)[:：]?\s*(\d+)', content)
        if lb_match:
            try:
                lb = int(lb_match.group(1))
            except ValueError:
                lb = None
        
        
        # 提取维度评分
        dimensions = self._extract_dimensions(content)
        
        # 提取问题列表
        problems = self._extract_problems(content)
        
        return EvaluationReport(
            report_id=report_id,
            project_name=project_name,
            generated_at=generated_at,
            total_score=total_score,
            rating=rating,
            dimensions=dimensions,
            problems=problems,
            raw_content=content,
            length_budget=lb
        )
    
    def _extract_project_name(self, file_path: str, content: str) -> str:
        """提取项目名"""
        # 尝试从路径提取
        if file_path:
            path_parts = Path(file_path).parts
            for part in path_parts:
                if "eval" not in part.lower() and part not in ['input', 'train', 'raw']:
                    return part
        
        # 从内容提取
        match = re.search(r'##?\s*(.+?)(?:虚拟实训|项目|课程)', content)
        if match:
            return match.group(1).strip()
        
        return "unknown"
    
    def _extract_datetime(self, content: str) -> str:
        """提取生成时间"""
        # 匹配格式：2026/02/01 14:52:26
        match = re.search(r'\*\*生成时间\*\*[:：]\s*(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})', content)
        if match:
            return match.group(1)
        
        # 文件名格式：evaluation-report-2026-02-01T06-52-26.md
        match = re.search(r'evaluation-report-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})', content)
        if match:
            return match.group(1).replace('T', ' ').replace('-', ':')
        
        return ""
    
    def _extract_total_score(self, content: str) -> float:
        """提取总分"""
        # 匹配格式：**总分**: 79.0 / 100
        match = re.search(r'\*\*总分\*\*[:：]\s*(\d+(?:\.\d+)?)', content)
        if match:
            return float(match.group(1))
        
        # 备选格式：总分: 79.0 / 100
        match = re.search(r'总分\s*[：:]\s*(\d+(?:\.\d+)?)', content)
        if match:
            return float(match.group(1))
        
        return 0.0
    
    def _extract_rating(self, content: str) -> str:
        """提取评级"""
        # 匹配格式：**评级**: 良好
        match = re.search(r'\*\*评级\*\*[:：]\s*(优秀|良好|合格|不合格|一票否决)', content)
        if match:
            return match.group(1)
        
        # 根据分数判断
        score = self._extract_total_score(content)
        if score >= 90:
            return "优秀"
        elif score >= 80:
            return "良好"
        elif score >= 60:
            return "合格"
        else:
            return "不合格"
    
    def _extract_dimensions(self, content: str) -> List[DimensionScore]:
        """提取维度评分"""
        dimensions = []
        
        # 查找维度评分表格
        table_pattern = r'\|\s*维度\s*\|\s*分数\s*\|\s*评级\s*\|\s*权重\s*\|\s*\n\|[-:\s|]+\n((?:\|[^\|]+\|[^\|]+\|[^\|]+\|[^\|]+\|\s*\n)+)'
        match = re.search(table_pattern, content)
        
        if match:
            table_content = match.group(1)
            rows = re.findall(r'\|\s*([^\|]+)\|\s*([^\|]+)\|\s*([^\|]+)\|\s*([^\|]+)\|', table_content)
            
            for row in rows:
                name = row[0].strip()
                try:
                    score = float(row[1].strip())
                except:
                    score = 0.0
                rating = row[2].strip()
                weight = row[3].strip()
                
                dimensions.append(DimensionScore(
                    name=name,
                    score=score,
                    max_score=20.0,  # 每个维度满分20
                    rating=rating,
                    weight=weight
                ))
        
        return dimensions
    
    def _extract_problems(self, content: str) -> List[Problem]:
        """提取问题列表"""
        problems = []
        
        # 查找发现问题部分
        # 格式：- **发现问题**:
        #       - **问题描述** (严重程度)
        #         > 位置: xxx
        #         > 引用: "xxx"
        
        problem_section = re.search(r'\*\*发现问题\*\*:([\s\S]*?)(?=\n\*\*|$)', content)
        if problem_section:
            section_content = problem_section.group(1)
            
            # 提取每个问题
            problem_pattern = r'- \*\*(.+?)\*\*\s*\((严重|一般)\)\s*\n\s*> 位置[:：]\s*(.+?)\n\s*> 引用[:：]\s*"(.+?)"'
            matches = re.findall(problem_pattern, section_content, re.DOTALL)
            
            for match in matches:
                problems.append(Problem(
                    description=match[0],
                    severity=match[1],
                    location=match[2].strip(),
                    evidence=match[3].strip()
                ))
        
        return problems
    
    def parse_directory(self, directory: str) -> List[EvaluationReport]:
        """解析目录中的所有评估报告"""
        reports = []
        path = Path(directory)
        
        # 查找所有markdown文件
        for md_file in path.rglob("*.md"):
            if "evaluation" in md_file.name.lower() or "eval" in md_file.name.lower():
                report = self.parse_file(str(md_file))
                if report:
                    reports.append(report)
        
        return reports
    
    def to_json(self, report: EvaluationReport) -> str:
        """将报告转换为JSON字符串"""
        data = {
            "report_id": report.report_id,
            "project_name": report.project_name,
            "generated_at": report.generated_at,
            "total_score": report.total_score,
            "rating": report.rating,
            "length_budget": report.length_budget,
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.score,
                    "max_score": d.max_score,
                    "rating": d.rating,
                    "weight": d.weight
                }
                for d in report.dimensions
            ],
            "problems": [
                {
                    "description": p.description,
                    "severity": p.severity,
                    "location": p.location,
                    "evidence": p.evidence
                }
                for p in report.problems
            ]
        }
        return json.dumps(data, ensure_ascii=False, indent=2)


def analyze_reports(reports: List[EvaluationReport]) -> Dict:
    """分析一批报告，生成统计信息"""
    if not reports:
        return {}
    
    scores = [r.total_score for r in reports]
    ratings = {}
    dimension_avg = {}
    problem_types = {}
    
    for report in reports:
        # 统计评级
        ratings[report.rating] = ratings.get(report.rating, 0) + 1
        
        # 统计维度平均分
        for dim in report.dimensions:
            if dim.name not in dimension_avg:
                dimension_avg[dim.name] = []
            dimension_avg[dim.name].append(dim.score)
        
        # 统计问题类型（简单按关键词分类）
        for problem in report.problems:
            desc = problem.description
            if "知识点" in desc or "覆盖" in desc:
                problem_types["知识点"] = problem_types.get("知识点", 0) + 1
            elif "机械" in desc or "句式" in desc or "重复" in desc:
                problem_types["表达机械"] = problem_types.get("表达机械", 0) + 1
            elif "长度" in desc or "字" in desc:
                problem_types["回复过长"] = problem_types.get("回复过长", 0) + 1
            elif "激励" in desc or "表扬" in desc:
                problem_types["缺少激励"] = problem_types.get("缺少激励", 0) + 1
            else:
                problem_types["其他"] = problem_types.get("其他", 0) + 1
    
    # 计算维度平均分
    for name, scores_list in dimension_avg.items():
        dimension_avg[name] = sum(scores_list) / len(scores_list)
    
    return {
        "total_reports": len(reports),
        "score_stats": {
            "min": min(scores),
            "max": max(scores),
            "avg": sum(scores) / len(scores),
            "above_85": len([s for s in scores if s >= 85]),
            "above_90": len([s for s in scores if s >= 90])
        },
        "rating_distribution": ratings,
        "dimension_averages": dimension_avg,
        "problem_type_distribution": problem_types
    }


if __name__ == "__main__":
    # 测试代码
    parser = EvaluationParser()
    
    # 解析当前项目的评估报告
    import os
    
    # 查找评估报告
    eval_dirs = [
        "input/现代农业创业项目路演_安康学院",
        "input/自动控制原理_山西大学",
        "外部评估报告"
    ]
    
    all_reports = []
    for eval_dir in eval_dirs:
        if os.path.exists(eval_dir):
            reports = parser.parse_directory(eval_dir)
            all_reports.extend(reports)
            print(f"从 {eval_dir} 解析了 {len(reports)} 个报告")
    
    if all_reports:
        # 分析统计
        stats = analyze_reports(all_reports)
        print("\n" + "="*60)
        print("评估报告统计分析")
        print("="*60)
        print(f"总报告数: {stats['total_reports']}")
        print(f"\n分数统计:")
        print(f"  最低分: {stats['score_stats']['min']}")
        print(f"  最高分: {stats['score_stats']['max']}")
        print(f"  平均分: {stats['score_stats']['avg']:.1f}")
        print(f"  ≥85分: {stats['score_stats']['above_85']} 个")
        print(f"  ≥90分: {stats['score_stats']['above_90']} 个")
        
        print(f"\n评级分布:")
        for rating, count in stats['rating_distribution'].items():
            print(f"  {rating}: {count} 个")
        
        print(f"\n维度平均分:")
        for dim, avg in stats['dimension_averages'].items():
            print(f"  {dim}: {avg:.1f}/20")
        
        print(f"\n高频问题类型:")
        for ptype, count in sorted(stats['problem_type_distribution'].items(), 
                                   key=lambda x: x[1], reverse=True):
            print(f"  {ptype}: {count} 次")
        
        # 保存为JSON
        output_dir = "output/processed"
        os.makedirs(output_dir, exist_ok=True)
        
        for report in all_reports:
            json_content = parser.to_json(report)
            output_file = os.path.join(output_dir, f"{report.report_id}.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(json_content)
        
        print(f"\n已保存 {len(all_reports)} 个报告的JSON文件到 {output_dir}/")
    else:
        print("未找到评估报告文件")
