"""
Trainset / Dev set 构建与加载
从剧本文件或目录解析出 (full_script, stages) 列表，供 DSPy 优化使用。
支持保存/加载为 JSON，以及结构校验与评估标准对齐检查。
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from parsers import parse_markdown, parse_docx, parse_doc, parse_pdf
from .content_splitter import ContentSplitter

from config import DEEPSEEK_API_KEY
import json
from pathlib import Path

# 卡片/输出目录（与 workspaces 或根目录 output 一致，不再使用 train/）
CARDS_ROOT = Path("output")

# 项目映射表（可选）：样本ID -> 项目名；无则留空
PROJECT_MAP: Dict[str, str] = {}
_projects_json = Path("output/project_map.json")
if _projects_json.exists():
    try:
        with open(_projects_json, "r", encoding="utf-8") as f:
            PROJECT_MAP = json.load(f)
    except Exception:
        pass


# ---------- 结构约定（与 ContentSplitter 输出及 DSPy 输入一致） ----------
TRAINSET_EXAMPLE_KEYS = {"full_script", "stages"}
STAGE_REQUIRED_KEYS = {"id", "title", "description", "role", "task", "key_points", "content_excerpt"}
STAGE_OPTIONAL_KEYS = {"interaction_rounds", "student_role"}

# 外部评估常见维度对应的剧本应含内容（用于对齐检查提示）
EVAL_ALIGNMENT_HINTS = {
    "任务目标": ["任务目标", "目标"],
    "评分标准": ["评分标准", "满分", "分"],
    "角色与场景": ["角色", "人设", "场景"],
    "阶段目标": ["task", "key_points"],
}


def _get_parser_for_path(file_path: str):
    """根据文件扩展名返回解析器函数。"""
    ext = os.path.splitext(file_path)[1].lower()
    parsers = {
        ".md": parse_markdown,
        ".docx": parse_docx,
        ".doc": parse_doc,
        ".pdf": parse_pdf,
    }
    if ext not in parsers:
        raise ValueError(f"不支持的文件格式: {ext}。支持: .md / .docx / .doc / .pdf")
    return parsers[ext]


def _parse_content(file_path: str) -> str:
    """解析单个文件得到原始文本内容。"""
    path = os.path.abspath(file_path)
    parser = _get_parser_for_path(path)
    return parser(path)


def build_trainset_from_path(
    path: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """
    从单个文件或目录构建 trainset。

    每条样本为 {"full_script": str, "stages": list}，其中 stages 为 ContentSplitter.analyze 返回的格式。

    Args:
        path: 文件路径或目录路径。目录时将递归查找 .md / .docx / .doc / .pdf。
        api_key: DeepSeek API 密钥（用于 ContentSplitter.analyze）；不传则用 config。
        verbose: 是否打印进度。

    Returns:
        样本列表，每项含 full_script 与 stages。
    """
    path = os.path.abspath(path)
    api_key = api_key or DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError("未提供 API 密钥，请在 .env 中设置 DEEPSEEK_API_KEY 或传入 api_key")

    files: List[str] = []
    if os.path.isfile(path):
        files = [path]
    elif os.path.isdir(path):
        for ext in (".md", ".docx", ".doc", ".pdf"):
            for f in Path(path).rglob(f"*{ext}"):
                files.append(str(f))
        files.sort()
    else:
        raise FileNotFoundError(f"路径不存在: {path}")

    if not files:
        raise ValueError(f"未在目录下找到 .md / .docx / .doc / .pdf 文件: {path}")

    splitter = ContentSplitter(api_key=api_key, base_url=base_url, model=model)
    examples: List[Dict[str, Any]] = []

    for i, fp in enumerate(files):
        if verbose:
            print(f"  [trainset] 处理 {i + 1}/{len(files)}: {os.path.basename(fp)}")
        try:
            content = _parse_content(fp)
            analysis = splitter.analyze(content)
            stages = analysis.get("stages", [])
            if not stages:
                if verbose:
                    print(f"    [跳过] 未识别出阶段: {fp}")
                continue
            examples.append({
                "full_script": content,
                "stages": stages,
                "source_file": fp,
            })
        except Exception as e:
            if verbose:
                print(f"    [错误] {fp}: {e}")
            raise

    return examples


def save_trainset(examples: List[Dict[str, Any]], json_path: str) -> None:
    """将样本列表保存为 JSON。stages 等可序列化结构原样写入。"""
    path = os.path.abspath(json_path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(examples, f, ensure_ascii=False, indent=2)


def load_trainset(json_path: str) -> List[Dict[str, Any]]:
    """从 JSON 文件加载样本列表。"""
    path = os.path.abspath(json_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"trainset 文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def append_trainset_example(
    full_script: str,
    stages: List[Dict[str, Any]],
    json_path: str,
    source_file: str = "",
) -> int:
    """
    将一条样本追加到 trainset.json；若已存在同 source_file 则替换。
    返回当前 trainset 条数。
    """
    path = os.path.abspath(json_path)
    try:
        examples = load_trainset(path)
    except FileNotFoundError:
        examples = []
    key = (source_file or "").strip()
    new_item = {"full_script": full_script, "stages": stages}
    if key:
        new_item["source_file"] = key
    if key:
        examples = [e for e in examples if (e.get("source_file") or "").strip() != key]
    examples.append(new_item)
    save_trainset(examples, path)
    return len(examples)


def validate_trainset(
    examples: List[Dict[str, Any]],
    strict: bool = False,
    check_eval_alignment: bool = True,
) -> Tuple[bool, List[str]]:
    """
    校验 trainset 结构与评估标准对齐情况。

    - 结构：每条样本必须有 full_script、stages；每个 stage 必须有 id, title, description, role, task, key_points, content_excerpt。
    - 对齐（可选）：full_script 建议包含任务目标/评分标准等，便于外部评估维度（知识点覆盖率、环节准出等）有据可依。

    Args:
        examples: 样本列表（load_trainset 或 build_trainset_from_path 的返回值）。
        strict: 若 True，任一项不通过即返回 valid=False；否则仅收集所有问题，结构齐全即 valid=True。
        check_eval_alignment: 是否做评估对齐的轻量检查（full_script 是否含任务目标/评分标准等）。

    Returns:
        (valid, messages): valid 表示是否通过；messages 为错误/警告列表。
    """
    messages: List[str] = []
    valid = True

    if not examples:
        messages.append("[错误] trainset 为空")
        return False, messages

    for idx, ex in enumerate(examples):
        if not isinstance(ex, dict):
            messages.append(f"样本 {idx + 1}: 应为 dict，实际为 {type(ex).__name__}")
            valid = False
            continue

        # 顶层键
        missing_top = TRAINSET_EXAMPLE_KEYS - set(ex.keys())
        if missing_top:
            messages.append(f"样本 {idx + 1}: 缺少键 {missing_top}")
            valid = False

        full_script = ex.get("full_script")
        stages = ex.get("stages")

        if full_script is not None and not isinstance(full_script, str):
            messages.append(f"样本 {idx + 1}: full_script 应为 str")
            valid = False
        if stages is not None and not isinstance(stages, list):
            messages.append(f"样本 {idx + 1}: stages 应为 list")
            valid = False

        if not stages:
            if full_script is not None:
                messages.append(f"样本 {idx + 1}: stages 为空，无法生成卡片")
            valid = False
            continue

        # 每个 stage 的必填字段
        for s_idx, stage in enumerate(stages):
            if not isinstance(stage, dict):
                messages.append(f"样本 {idx + 1} 阶段 {s_idx + 1}: 应为 dict")
                valid = False
                continue
            missing_stage = STAGE_REQUIRED_KEYS - set(stage.keys())
            if missing_stage:
                messages.append(f"样本 {idx + 1} 阶段 {s_idx + 1}: 缺少 {missing_stage}")
                if strict:
                    valid = False
            # 非空检查
            for key in ("title", "task", "key_points", "content_excerpt"):
                val = stage.get(key)
                if val is None or (key == "key_points" and (not isinstance(val, list) or len(val) == 0)):
                    if key == "key_points":
                        messages.append(f"样本 {idx + 1} 阶段 {s_idx + 1}: key_points 应为非空列表")
                    else:
                        messages.append(f"样本 {idx + 1} 阶段 {s_idx + 1}: {key} 为空")
                    if strict:
                        valid = False

        # 评估对齐：full_script 建议包含任务目标、评分标准等
        if check_eval_alignment and full_script and isinstance(full_script, str):
            if "任务目标" not in full_script and "目标" not in full_script:
                messages.append(f"样本 {idx + 1}: [建议] full_script 中未见「任务目标」类表述，评估时「目标达成度」等维度可能缺少依据")
            if "评分标准" not in full_script and "满分" not in full_script:
                messages.append(f"样本 {idx + 1}: [建议] full_script 中未见「评分标准」或「满分」，与外部评估维度对齐时可补充")

    if strict and messages:
        valid = False
    elif not valid:
        pass  # 已因结构错误设为 False
    else:
        valid = not any(m.startswith("[错误]") for m in messages)

    return valid, messages


def check_trainset_file(json_path: str, strict: bool = False, check_eval_alignment: bool = True) -> Tuple[bool, List[str]]:
    """
    加载指定 JSON 后执行 validate_trainset，便于 CLI 或脚本调用。

    Returns:
        (valid, messages)
    """
    examples = load_trainset(json_path)
    return validate_trainset(examples, strict=strict, check_eval_alignment=check_eval_alignment)


# ==================== 与评估报告集成的扩展功能 ====================

from .evaluation_parser import EvaluationParser, EvaluationReport
from dataclasses import dataclass, asdict


@dataclass
class TrainExampleWithEval:
    """带评估信息的训练样本"""
    example_id: str
    project_name: str
    full_script: str
    stages: List[Dict[str, Any]]
    generated_cards: str
    evaluation_score: float
    dimension_scores: Dict[str, float]
    problems: List[Dict[str, Any]]
    is_golden: bool = False  # 90+分
    is_pass: bool = False    # 85+分
    length_budget: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    def to_dspy_format(self) -> Dict[str, Any]:
        """转换为DSPy训练格式"""
        return {
            "full_script": self.full_script,
            "stages": self.stages,
            "cards": self.generated_cards,
            "score": self.evaluation_score
        }


class EvaluationAwareBuilder:
    """支持评估报告的训练集构建器"""
    
    def __init__(self, 
                 train_dir: str = "train",
                 golden_threshold: float = 90.0,
                 pass_threshold: float = 85.0):
        self.train_dir = Path(train_dir)
        self.golden_threshold = golden_threshold
        self.pass_threshold = pass_threshold
        self.parser = EvaluationParser()
        self._ensure_directories()
        
    def _default_length_budget(self, project_name: str) -> int:
        """简单预算推断：为不同项目返回一个默认长度预算（字数）"""
        # 基本统一预算，必要时可扩展到基于项目的映射
        budget = 340
        if project_name:
            if '自动' in project_name:
                budget = 320
            if '现代' in project_name:
                budget = 360
            if '路演' in project_name:
                budget = 330
        return budget
    
    def _ensure_directories(self):
        """确保目录结构存在，支持新的训练数据分区"""
        dirs = [
            self.train_dir / "raw" / "scripts",
            self.train_dir / "raw" / "evaluations",
            self.train_dir / "raw" / "cards",
            self.train_dir / "external" / "evaluations",
            self.train_dir / "generated",
            self.train_dir / "processed",
            self.train_dir / "optimizer" / "bootstrap" / "logs",
            self.train_dir / "optimizer" / "bootstrap" / "examples",
            self.train_dir / "logs",
            self.train_dir / "output"
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
    
    def build_from_evaluations(self, 
                               eval_dir: str,
                               cards_dir: str,
                               scripts_dir: str) -> List[TrainExampleWithEval]:
        """
        从评估报告构建带评估信息的训练集
        
        Args:
            eval_dir: 评估报告目录
            cards_dir: 生成的卡片目录
            scripts_dir: 原材料剧本目录
            
        Returns:
            带评估信息的训练样本列表
        """
        examples = []
        
        # 解析所有评估报告
        reports = self.parser.parse_directory(eval_dir)
        print(f"从 {eval_dir} 解析了 {len(reports)} 个评估报告")
        
        for report in reports:
            # 查找对应的卡片文件
            cards_content = self._find_matching_file(
                report.project_name, 
                report.report_id, 
                str(CARDS_ROOT), 
                ['.md', '.txt']
            )
            
            if not cards_content:
                print(f"警告: 未找到 {report.report_id} 对应的卡片文件")
                continue
            
            # 查找对应的原材料
            script_content = self._find_matching_file(
                report.project_name,
                report.report_id,
                scripts_dir,
                ['.md', '.docx', '.doc', '.pdf', '.txt']
            ) or ""
            
            # 从卡片中提取stages
            stages = self._extract_stages_from_cards(cards_content)
            
            # 构建训练样本
            # determine budget: use report budget if present, else default per project
            budget = report.length_budget if getattr(report, 'length_budget', None) is not None else self._default_length_budget(report.project_name)
            example = TrainExampleWithEval(
                example_id=report.report_id,
                project_name=report.project_name,
                full_script=script_content,
                stages=stages,
                generated_cards=cards_content,
                evaluation_score=report.total_score,
                dimension_scores={d.name: d.score for d in report.dimensions},
                problems=[
                    {
                        "description": p.description,
                        "severity": p.severity,
                        "location": p.location
                    }
                    for p in report.problems
                ],
                is_golden=report.total_score >= self.golden_threshold,
                is_pass=report.total_score >= self.pass_threshold,
                length_budget=budget
            )
            
            examples.append(example)
        
        return examples
    
    def _find_matching_file(self, project_name: str, report_id: str, 
                           search_dir: str, extensions: List[str]) -> Optional[str]:
        """查找匹配的文件"""
        search_path = Path(search_dir)
        # 使用 project_map 的映射（如果有）来覆盖项目名
        mapped = PROJECT_MAP.get(report_id)
        if mapped:
            project_name = mapped
        if not search_path.exists():
            return None
        
        # 策略1: 项目名匹配
        for ext in extensions:
            for file in search_path.rglob(f"*{ext}"):
                if project_name.lower() in file.name.lower():
                    return file.read_text(encoding='utf-8')
        
        # 策略2: report_id前缀匹配
        report_prefix = report_id.split('_')[0] if '_' in report_id else report_id
        for ext in extensions:
            for file in search_path.rglob(f"*{ext}"):
                if report_prefix.lower() in file.name.lower():
                    return file.read_text(encoding='utf-8')
        
        return None
    
    def _extract_stages_from_cards(self, cards_content: str) -> List[Dict[str, Any]]:
        """从卡片内容中提取stages"""
        import re
        stages = []
        
        # 按卡片分割
        card_sections = re.split(r'# 卡片[\dA-Za-z]+\n\n', cards_content)
        
        for i, section in enumerate(card_sections[1:], 1):
            # 提取Role、Context、Interaction等部分
            stage = {
                "id": i,
                "title": f"第{i}幕",
                "description": "",
                "role": "",
                "task": "",
                "key_points": [],
                "content_excerpt": section[:500] if len(section) > 500 else section
            }
            
            # 简单提取role
            role_match = re.search(r'# Role\n(.+?)(?=\n#|$)', section, re.DOTALL)
            if role_match:
                stage["role"] = role_match.group(1).strip()[:200]
            
            # 简单提取task（从Context或Interaction中推断）
            task_match = re.search(r'# Context\n(.+?)(?=\n#|$)', section, re.DOTALL)
            if task_match:
                stage["task"] = task_match.group(1).strip()[:200]
            
            stages.append(stage)
        
        return stages
    
    def save_eval_trainset(self, examples: List[TrainExampleWithEval], 
                          filename: str = "trainset_with_eval.json") -> str:
        """保存带评估信息的训练集"""
        output_path = self.train_dir / "processed" / filename
        
        trainset_data = {
            "metadata": {
                "total_examples": len(examples),
                "golden_examples": len([e for e in examples if e.is_golden]),
                "pass_examples": len([e for e in examples if e.is_pass]),
                "fail_examples": len([e for e in examples if not e.is_pass]),
                "avg_score": sum(e.evaluation_score for e in examples) / len(examples) if examples else 0,
                "score_distribution": self._calc_score_distribution(examples)
            },
            "examples": [e.to_dict() for e in examples]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(trainset_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n训练集已保存: {output_path}")
        meta = trainset_data['metadata']
        print(f"  总样本: {meta['total_examples']}")
        print(f"  黄金标准(≥90): {meta['golden_examples']}")
        print(f"  及格(≥85): {meta['pass_examples']}")
        print(f"  不及格(<85): {meta['fail_examples']}")
        print(f"  平均分: {meta['avg_score']:.1f}")
        
        return str(output_path)
    
    def _calc_score_distribution(self, examples: List[TrainExampleWithEval]) -> Dict[str, int]:
        """计算分数分布"""
        distribution = {"90-100": 0, "85-89": 0, "80-84": 0, "70-79": 0, "60-69": 0, "<60": 0}
        
        for e in examples:
            score = e.evaluation_score
            if score >= 90:
                distribution["90-100"] += 1
            elif score >= 85:
                distribution["85-89"] += 1
            elif score >= 80:
                distribution["80-84"] += 1
            elif score >= 70:
                distribution["70-79"] += 1
            elif score >= 60:
                distribution["60-69"] += 1
            else:
                distribution["<60"] += 1
        
        return distribution
    
    def select_best_examples(self, examples: List[TrainExampleWithEval], 
                            n: int = 4) -> List[TrainExampleWithEval]:
        """选择最好的n个样本作为few-shot示例"""
        sorted_examples = sorted(
            examples,
            key=lambda e: (e.is_golden, e.evaluation_score),
            reverse=True
        )
        return sorted_examples[:n]
    
    def get_problem_analysis(self, examples: List[TrainExampleWithEval]) -> Dict[str, Any]:
        """分析问题分布，找出高频扣分点"""
        all_problems = []
        for e in examples:
            all_problems.extend(e.problems)
        
        # 按严重程度分类
        severe_problems = [p for p in all_problems if p.get('severity') == '严重']
        general_problems = [p for p in all_problems if p.get('severity') == '一般']
        
        # 关键词统计
        keywords = {}
        for p in all_problems:
            desc = p.get('description', '')
            # 提取关键词
            for kw in ['知识点', '机械', '句式', '重复', '长度', '字', '激励', '表扬', 
                      '环节', '跳转', '流程', '角色', '人设', '数据', '事实']:
                if kw in desc:
                    keywords[kw] = keywords.get(kw, 0) + 1
        
        return {
            "total_problems": len(all_problems),
            "severe_count": len(severe_problems),
            "general_count": len(general_problems),
            "top_keywords": sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:10],
            "sample_severe": severe_problems[:3] if severe_problems else [],
            "sample_general": general_problems[:3] if general_problems else []
        }


# 便捷函数：快速构建带评估的训练集
def quick_build_eval_trainset(
    eval_dirs: Optional[List[str]] = None,
    cards_dirs: Optional[List[str]] = None,
    scripts_dirs: Optional[List[str]] = None,
    train_dir: str = "train"
) -> str:
    """
    快速构建带评估信息的训练集
    
    自动查找常见目录并构建训练集
    """
    if eval_dirs is None:
        eval_dirs = [
            "input/现代农业创业项目路演_安康学院",
            "input/自动控制原理_山西大学",
            "外部评估报告",
        ]
    if cards_dirs is None:
        cards_dirs = [str(CARDS_ROOT)]
    if scripts_dirs is None:
        scripts_dirs = ["input"]
    
    builder = EvaluationAwareBuilder(train_dir=train_dir)
    all_examples = []
    
    # 尝试所有目录组合
    for eval_dir in eval_dirs:
        if not os.path.exists(eval_dir):
            continue
            
        for cards_dir in cards_dirs:
            if not os.path.exists(cards_dir):
                continue
                
            for scripts_dir in scripts_dirs:
                if not os.path.exists(scripts_dir):
                    continue
                
                try:
                    examples = builder.build_from_evaluations(
                        eval_dir, cards_dir, scripts_dir
                    )
                    all_examples.extend(examples)
                    print(f"  从 {eval_dir} 构建了 {len(examples)} 个样本")
                except Exception as e:
                    print(f"  构建失败 {eval_dir}: {e}")
    
    if all_examples:
        # 去重
        unique_examples = {}
        for e in all_examples:
            unique_examples[e.example_id] = e
        all_examples = list(unique_examples.values())
        
        # 保存
        output_path = builder.save_eval_trainset(all_examples)
        
        # 问题分析
        analysis = builder.get_problem_analysis(all_examples)
        print(f"\n问题分析:")
        print(f"  总问题数: {analysis['total_problems']}")
        print(f"  严重问题: {analysis['severe_count']}")
        print(f"  高频关键词: {[kw for kw, _ in analysis['top_keywords'][:5]]}")
        
        return output_path
    else:
        print("未找到训练数据")
        return ""
