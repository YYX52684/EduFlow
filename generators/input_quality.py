"""
原材料质量检查与预处理模块
在生成卡片前检查并改善输入质量
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class QualityReport:
    """质量检查报告"""
    score: float  # 0-100 分
    issues: List[str]
    warnings: List[str]
    suggestions: List[str]
    is_pass: bool


class InputQualityChecker:
    """输入质量检查器"""

    def __init__(
        self,
        min_stage_content_length: int = 100,
        max_stage_content_length: int = 2000,
        min_role_description_length: int = 10,
        min_stages: int = 1,
        max_stages: int = 10,
    ):
        self.min_stage_content_length = min_stage_content_length
        self.max_stage_content_length = max_stage_content_length
        self.min_role_description_length = min_role_description_length
        self.min_stages = min_stages
        self.max_stages = max_stages

    def check(self, stages: List[dict], full_script: str) -> QualityReport:
        """
        全面检查输入质量
        
        Returns:
            QualityReport 包含分数、问题列表和改进建议
        """
        issues = []
        warnings = []
        suggestions = []
        score = 100

        # 1. 检查阶段数量
        if len(stages) < self.min_stages:
            issues.append(f"阶段数量过少：只有 {len(stages)} 个阶段，至少需要 {self.min_stages} 个")
            score -= 30
        elif len(stages) > self.max_stages:
            warnings.append(f"阶段数量较多：{len(stages)} 个阶段，建议控制在 {self.max_stages} 个以内")
            score -= 10

        # 2. 检查每个阶段的内容质量
        for i, stage in enumerate(stages, 1):
            stage_issues, stage_warnings, stage_score = self._check_stage(stage, i)
            issues.extend(stage_issues)
            warnings.extend(stage_warnings)
            score -= stage_score

        # 3. 检查整体剧本质量
        script_issues, script_warnings, script_score = self._check_script(full_script)
        issues.extend(script_issues)
        warnings.extend(script_warnings)
        score -= script_score

        # 4. 检查阶段间连贯性
        continuity_issues = self._check_continuity(stages)
        if continuity_issues:
            warnings.extend(continuity_issues)
            score -= 5 * len(continuity_issues)

        # 生成改进建议
        suggestions = self._generate_suggestions(issues, warnings, stages)

        # 确保分数在合理范围
        score = max(0, min(100, score))
        is_pass = score >= 60 and len(issues) == 0

        return QualityReport(
            score=score,
            issues=issues,
            warnings=warnings,
            suggestions=suggestions,
            is_pass=is_pass
        )

    def _check_stage(self, stage: dict, stage_index: int) -> Tuple[List[str], List[str], float]:
        """检查单个阶段的质量"""
        issues = []
        warnings = []
        score = 0

        prefix = f"第{stage_index}幕"

        # 检查必需字段
        required_fields = ['title', 'role', 'task', 'content_excerpt']
        for field in required_fields:
            if not stage.get(field):
                issues.append(f"{prefix} 缺少必要字段：{field}")
                score += 15

        # 检查内容长度
        content = stage.get('content_excerpt', '')
        if len(content) < self.min_stage_content_length:
            if len(content) == 0:
                issues.append(f"{prefix} 内容为空")
                score += 20
            else:
                warnings.append(f"{prefix} 内容较短（{len(content)}字），建议至少 {self.min_stage_content_length} 字")
                score += 5
        elif len(content) > self.max_stage_content_length:
            warnings.append(f"{prefix} 内容较长（{len(content)}字），建议精简到 {self.max_stage_content_length} 字以内")
            score += 5

        # 检查角色描述
        role = stage.get('role', '')
        if len(role) < self.min_role_description_length:
            warnings.append(f"{prefix} 角色描述较短（{len(role)}字），建议详细描述角色身份、性格")
            score += 5

        # 检查任务清晰度
        task = stage.get('task', '')
        if not task or len(task) < 10:
            warnings.append(f"{prefix} 任务/目标描述不清晰")
            score += 5

        # 检查关键点
        key_points = stage.get('key_points', [])
        if not key_points:
            warnings.append(f"{prefix} 未设置关键点，建议添加本阶段需要掌握的知识点")
            score += 3

        # 检查文本质量问题
        text_issues = self._check_text_quality(content)
        for issue in text_issues:
            warnings.append(f"{prefix} {issue}")
            score += 3

        return issues, warnings, score

    def _check_script(self, script: str) -> Tuple[List[str], List[str], float]:
        """检查整体剧本质量"""
        issues = []
        warnings = []
        score = 0

        if not script or len(script.strip()) == 0:
            issues.append("原始剧本内容为空")
            return issues, warnings, 50

        # 检查剧本长度
        if len(script) < 500:
            warnings.append("原始剧本内容较短，可能影响生成质量")
            score += 10
        elif len(script) > 10000:
            warnings.append("原始剧本内容较长，建议精简核心情节")
            score += 5

        # 检查文本质量问题
        text_issues = self._check_text_quality(script)
        for issue in text_issues:
            if "特殊字符" in issue:
                warnings.append(f"剧本中包含{issue}")
            else:
                warnings.append(f"剧本{issue}")
            score += 3

        # 检查结构清晰度
        if not re.search(r'[一二三四五六七八九十123456789]+[、.．]|第[一二三四五六七八九十123456789]+幕|场景\d+', script):
            warnings.append("剧本中未检测到明确的阶段划分标记（如"第1幕"、"场景1"等）")
            score += 10

        return issues, warnings, score

    def _check_text_quality(self, text: str) -> List[str]:
        """检查文本质量问题"""
        issues = []

        # 检查特殊字符
        special_chars = re.findall(r'[^\u4e00-\u9fff\u3000-\u303fa-zA-Z0-9\s.,;:!?，。、；：！？""''（）()【】[]]', text)
        if special_chars:
            unique_chars = set(special_chars[:10])  # 只显示前10个不同的
            issues.append(f"特殊字符：{''.join(unique_chars)}")

        # 检查连续空格
        if re.search(r' {3,}', text):
            issues.append("包含连续多个空格")

        # 检查连续换行
        if re.search(r'\n{4,}', text):
            issues.append("包含过多空行")

        # 检查中英文标点混用
        if re.search(r'[，。！？；：][,.!?;:]|[,.!?;:][，。！？；：]', text):
            issues.append("中英文标点混用")

        # 检查重复字符
        if re.search(r'(.)\1{4,}', text):
            issues.append("包含重复字符（如"啊啊啊啊"）")

        return issues

    def _check_continuity(self, stages: List[dict]) -> List[str]:
        """检查阶段间连贯性"""
        warnings = []

        if len(stages) < 2:
            return warnings

        # 检查角色连贯性
        for i in range(len(stages) - 1):
            current_role = stages[i].get('role', '')
            next_role = stages[i + 1].get('role', '')

            if not current_role or not next_role:
                continue

            # 如果角色突然变化但没有明确说明，给出警告
            current_name = current_role.split('，')[0].split(',')[0].strip()
            next_name = next_role.split('，')[0].split(',')[0].strip()

            if current_name != next_name:
                warnings.append(f"第{i+1}幕到第{i+2}幕角色从"{current_name}"变为"{next_name}"，请确保有合理的过渡")

        # 检查任务连贯性
        for i in range(len(stages) - 1):
            current_task = stages[i].get('task', '')
            next_task = stages[i + 1].get('task', '')

            if not current_task or not next_task:
                continue

            # 简单的连贯性检查：如果任务完全相同，可能是复制粘贴错误
            if current_task == next_task:
                warnings.append(f"第{i+1}幕和第{i+2}幕的任务完全相同，请检查是否有误")

        return warnings

    def _generate_suggestions(
        self,
        issues: List[str],
        warnings: List[str],
        stages: List[dict]
    ) -> List[str]:
        """生成改进建议"""
        suggestions = []

        if any("缺少" in issue for issue in issues):
            suggestions.append("📋 **完善阶段信息**：确保每个阶段都有标题、角色、任务和内容简介")

        if any("内容为空" in issue for issue in issues):
            suggestions.append("📝 **补充内容**：在 content_excerpt 字段中添加该阶段的核心剧情")

        if any("角色" in warning for warning in warnings):
            suggestions.append("👤 **详细描述角色**：包括姓名、身份、性格特点、说话风格等")

        if any("关键点" in warning for warning in warnings):
            suggestions.append("🎯 **添加关键点**：列出每个阶段需要学生掌握的核心知识点或技能")

        if any("标点" in warning for warning in warnings):
            suggestions.append("✏️ **统一标点**：建议使用中文标点，避免中英文混用")

        if any("阶段划分" in warning for warning in warnings):
            suggestions.append("📑 **明确结构**：在剧本中使用"第1幕"、"场景1"等标记划分不同阶段")

        if len(stages) > 6:
            suggestions.append("✂️ **精简阶段**：建议将复杂场景拆分为多个训练，每轮训练 3-5 个阶段效果最佳")

        if not suggestions:
            suggestions.append("✅ 基本信息完整，可以考虑增加更多细节来提升生成质量")

        return suggestions


class InputPreprocessor:
    """输入预处理器：自动修复常见问题"""

    def preprocess(self, stages: List[dict], full_script: str) -> Tuple[List[dict], str]:
        """
        预处理输入数据，修复常见问题
        
        Returns:
            (处理后的 stages, 处理后的 full_script)
        """
        # 1. 清理文本
        full_script = self._clean_text(full_script)

        # 2. 处理每个阶段
        processed_stages = []
        for stage in stages:
            processed_stage = self._clean_stage(stage)
            processed_stages.append(processed_stage)

        # 3. 自动补充缺失字段
        processed_stages = self._fill_missing_fields(processed_stages, full_script)

        return processed_stages, full_script

    def _clean_text(self, text: str) -> str:
        """清理文本"""
        if not text:
            return text

        # 标准化换行符
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # 移除连续空行（保留最多2个）
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 移除行首行尾空格
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)

        # 标准化空格
        text = re.sub(r' {2,}', ' ', text)

        # 中英文标点标准化（可选，根据需要开启）
        # text = text.replace(',', '，').replace('.', '。')

        return text.strip()

    def _clean_stage(self, stage: dict) -> dict:
        """清理单个阶段的数据"""
        cleaned = stage.copy()

        # 清理字符串字段
        for key in ['title', 'role', 'task', 'content_excerpt']:
            if key in cleaned and isinstance(cleaned[key], str):
                cleaned[key] = self._clean_text(cleaned[key])

        # 清理关键点列表
        if 'key_points' in cleaned and isinstance(cleaned['key_points'], list):
            cleaned['key_points'] = [
                self._clean_text(kp) for kp in cleaned['key_points'] if kp
            ]

        return cleaned

    def _fill_missing_fields(self, stages: List[dict], full_script: str) -> List[dict]:
        """自动填充缺失字段"""
        filled_stages = []

        for i, stage in enumerate(stages, 1):
            filled = stage.copy()

            # 如果没有标题，生成默认标题
            if not filled.get('title'):
                filled['title'] = f"第{i}幕"

            # 如果没有内容摘要，尝试从剧本中提取
            if not filled.get('content_excerpt') and full_script:
                excerpt = self._extract_excerpt(full_script, i, len(stages))
                filled['content_excerpt'] = excerpt

            # 如果没有角色，尝试从剧本中推断（简化版）
            if not filled.get('role') and full_script:
                # 这里可以添加更复杂的角色提取逻辑
                filled['role'] = "请填写角色信息"

            # 如果没有任务
            if not filled.get('task'):
                filled['task'] = f"完成第{i}幕的交互训练"

            # 如果没有关键点，设置空列表
            if 'key_points' not in filled:
                filled['key_points'] = []

            filled_stages.append(filled)

        return filled_stages

    def _extract_excerpt(self, script: str, stage_index: int, total_stages: int) -> str:
        """从剧本中提取阶段内容摘要（简化版）"""
        # 按常见分隔符分割剧本
        parts = re.split(r'\n(?=第[一二三四五六七八九十123456789]+幕|场景\d+|【场景|\[Scene)', script)

        if len(parts) >= total_stages:
            # 尝试找到对应阶段
            idx = min(stage_index - 1, len(parts) - 1)
            excerpt = parts[idx].strip()
            # 限制长度
            if len(excerpt) > 1000:
                excerpt = excerpt[:1000] + "..."
            return excerpt

        # 如果分割失败，返回剧本前 500 字
        if len(script) > 500:
            return script[:500] + "..."
        return script


# ========== 便捷使用函数 ==========

def check_and_fix_input(
    stages: List[dict],
    full_script: str,
    auto_fix: bool = True,
    strict_mode: bool = False
) -> Tuple[QualityReport, List[dict], str]:
    """
    一站式输入质量检查和修复

    Args:
        stages: 阶段列表
        full_script: 完整剧本
        auto_fix: 是否自动修复常见问题
        strict_mode: 严格模式（质量分数低于60时拒绝）

    Returns:
        (质量报告, 处理后的stages, 处理后的full_script)
    """
    # 1. 质量检查
    checker = InputQualityChecker()
    report = checker.check(stages, full_script)

    # 2. 自动修复（如果开启）
    if auto_fix:
        preprocessor = InputPreprocessor()
        stages, full_script = preprocessor.preprocess(stages, full_script)

        # 修复后重新检查
        report = checker.check(stages, full_script)

    # 3. 严格模式检查
    if strict_mode and not report.is_pass:
        raise ValueError(
            f"输入质量检查未通过（得分：{report.score}）。\n"
            f"问题：{report.issues}\n"
            f"建议：{report.suggestions}"
        )

    return report, stages, full_script


if __name__ == "__main__":
    # 测试代码
    print("测试输入质量检查器...")

    # 模拟一个质量不好的输入
    test_stages = [
        {
            "title": "第一幕",
            "role": "医生",
            "task": "问诊",
            "content_excerpt": "",  # 空的！
            "key_points": []
        },
        {
            "title": "第二幕",
            "role": "医生",  # 重复角色
            "task": "问诊",  # 重复任务
            "content_excerpt": "这是第二幕的内容...",
            "key_points": ["倾听", "沟通"]
        }
    ]

    test_script = """第一幕内容...



第二幕内容..."""  # 包含过多空行

    report, fixed_stages, fixed_script = check_and_fix_input(
        test_stages, test_script, auto_fix=True
    )

    print(f"\n质量评分：{report.score}/100")
    print(f"是否通过：{'是' if report.is_pass else '否'}")
    print(f"\n问题：{report.issues}")
    print(f"\n警告：{report.warnings}")
    print(f"\n建议：{report.suggestions}")
