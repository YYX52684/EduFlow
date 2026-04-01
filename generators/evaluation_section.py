"""
评价项 Markdown 章节生成
在生成的卡片 Markdown 末尾追加 ## 评价项（供注入时解析，不影响卡片提示词）
"""
from typing import List, Dict, Any


def build_evaluation_markdown(
    evaluation_items: List[Dict[str, Any]],
    stages: List[Dict[str, Any]],
    target_total_score: int = 100,
    auto_generate_if_empty: bool = True,
) -> str:
    """
    生成 ## 评价项 章节的 Markdown 文本。

    - 若 evaluation_items 非空，直接使用并格式化为统一结构。
    - 否则若 auto_generate_if_empty 为 True，根据 stages 自动生成（每阶段约 target_total_score/N 分）。

    Args:
        evaluation_items: 从原文档解析出的评价项，每项含 item_name, score, description, require_detail
        stages: 阶段列表，每项含 id, title, task, key_points 等
        target_total_score: 目标总分（自动生成时用）
        auto_generate_if_empty: 无评价项时是否按阶段自动生成

    Returns:
        评价项章节的 Markdown 字符串（含 ## 评价项 标题），无内容时返回空字符串。
    """
    if evaluation_items:
        return _format_evaluation_items(evaluation_items)

    if not auto_generate_if_empty or not stages:
        return ""

    # 按阶段自动生成：每阶段 100/N 分（向下取整到 5 的倍数）
    n = len(stages)
    base_score = (target_total_score // n) // 5 * 5
    remainder = target_total_score - base_score * n
    items = []
    for i, stage in enumerate(stages):
        score = base_score + (1 if i < remainder else 0)
        if score <= 0:
            score = 5
        title = stage.get("title", f"阶段{stage.get('id', i + 1)}")
        task = (stage.get("task") or "").strip()
        role = (stage.get("role") or "").strip()
        excerpt = (stage.get("content_excerpt") or "").strip()
        key_points = stage.get("key_points") or []

        desc_parts = []
        if task:
            desc_parts.append(task[:420] + ("…" if len(task) > 420 else ""))
        if excerpt and excerpt not in task:
            desc_parts.append("内容要点摘录：" + excerpt[:320] + ("…" if len(excerpt) > 320 else ""))
        if role:
            desc_parts.append("本阶段智能体角色定位：" + role[:200] + ("…" if len(role) > 200 else ""))
        description = "\n".join(desc_parts) if desc_parts else f"综合考察学员在「{title}」环节的理解、操作与表达是否达到教学目标。"

        kp_text = "、".join(str(x).strip() for x in key_points[:8] if str(x).strip())
        req_parts = []
        if kp_text:
            req_parts.append("须体现以下要点：" + kp_text)
        if role:
            req_parts.append("对话风格与人设须符合角色设定。")
        req_parts.append("完成该阶段交互目标，逻辑清晰、无明显事实性错误。")
        require_detail = "；".join(req_parts)

        items.append({
            "item_name": f"{title}完成度",
            "score": score,
            "description": description,
            "require_detail": require_detail,
        })
    return _format_evaluation_items(items)


def _format_evaluation_items(items: List[Dict[str, Any]]) -> str:
    """将评价项列表格式化为 Markdown"""
    if not items:
        return ""
    lines = ["## 评价项", ""]
    for i, it in enumerate(items, 1):
        name = it.get("item_name", f"评价项{i}")
        score = it.get("score", 0)
        desc = (it.get("description") or "").replace("\n", " ").strip()
        req = (it.get("require_detail") or "").replace("\n", " ").strip()
        lines.append(f"### 评价项{i}：{name}")
        lines.append(f"- **满分值**: {score}")
        if desc:
            lines.append(f"- **评价描述**: {desc}")
        if req:
            lines.append(f"- **详细要求**: {req}")
        lines.append("")
    return "\n".join(lines).strip()
