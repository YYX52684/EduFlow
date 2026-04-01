"""
能力训练文档：规范化与校验（不依赖 LLM，便于单测）。
"""

from __future__ import annotations

import re
from typing import List, Tuple

from config import TRAINING_DOC_CONFIG

# 与签名、配置保持一致的二级标题（不含 ## 前缀）
REQUIRED_H2_TITLES: Tuple[str, ...] = tuple(TRAINING_DOC_CONFIG["section_h2_titles"])

# 中文紧邻英文时 \b 往往不生效，故用语境边界而非纯单词边界
_PPT_PATTERN = re.compile(
    r"(?i)(?<![a-z])powerpoint(?![a-z])|(?<![a-z])ppt(?![a-z])|幻灯片"
)
_DISALLOWED_TERMS = ("ppt", "powerpoint", "幻灯片")

_SCORE_FEN_PATTERN = re.compile(r"(\d+)\s*分")


def normalize_training_doc_markdown(text: str) -> str:
    """术语替换、轻量清理。"""
    if not text or not text.strip():
        return text
    out = text.strip()
    out = _PPT_PATTERN.sub("所给图片", out)
    return out


def _extract_h2_sections(text: str) -> List[Tuple[str, str]]:
    """按 ## 二级标题切分；返回 [(标题, 内容含子标题), ...]。"""
    lines = text.splitlines()
    sections: List[Tuple[str, str]] = []
    current_title: str | None = None
    current_buf: List[str] = []

    for line in lines:
        m = re.match(r"^##\s+(.+?)\s*$", line.strip())
        if m:
            if current_title is not None:
                sections.append((current_title, "\n".join(current_buf).strip()))
            current_title = m.group(1).strip()
            current_buf = []
        else:
            current_buf.append(line)

    if current_title is not None:
        sections.append((current_title, "\n".join(current_buf).strip()))
    return sections


def _h2_order_ok(titles_found: List[str]) -> bool:
    if len(titles_found) < len(REQUIRED_H2_TITLES):
        return False
    req = list(REQUIRED_H2_TITLES)
    j = 0
    for t in titles_found:
        if j < len(req) and t == req[j]:
            j += 1
    return j == len(req)


def _section_text(text: str, h2_title: str) -> str:
    for title, body in _extract_h2_sections(text):
        if title == h2_title:
            return body
    return ""


def _count_h3_in_section(section_body: str) -> int:
    return sum(1 for line in section_body.splitlines() if re.match(r"^###\s+\S", line.strip()))


def _parse_score_sum_from_evaluation(section_body: str) -> int | None:
    """从「评价标准」节 Markdown 表格中累加「对应分值」列（通常为第 3 列）。"""
    if not section_body.strip():
        return None
    total = 0
    data_rows = 0
    for raw_line in section_body.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c]
        if len(cells) < 3:
            continue
        joined = "".join(cells)
        if "评分项" in joined and "对应分值" in joined:
            continue
        if all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells):
            continue
        score_cell = cells[2]
        m = _SCORE_FEN_PATTERN.search(score_cell)
        if m:
            total += int(m.group(1))
            data_rows += 1
    if data_rows > 0:
        return total
    ms = list(_SCORE_FEN_PATTERN.finditer(section_body))
    if not ms:
        return None
    return sum(int(m.group(1)) for m in ms)


def validate_training_doc_markdown(text: str) -> Tuple[bool, List[str]]:
    """
    校验 Markdown 结构、禁用词、评价总分、板块与话术示例数量（启发式）。
    """
    errors: List[str] = []
    if not text or not text.strip():
        return False, ["文档为空"]

    lower = text.lower()
    for term in _DISALLOWED_TERMS:
        if term.lower() in lower:
            errors.append(f"包含禁用表述：{term}")

    sections = _extract_h2_sections(text)
    titles_found = [t for t, _ in sections]
    if not _h2_order_ok(titles_found):
        errors.append(
            f"二级标题顺序或缺失：需要依次出现 {list(REQUIRED_H2_TITLES)}，实际为 {titles_found}"
        )

    req_body = _section_text(text, "智能体各板块任务要求")
    if req_body:
        if "各板块互动话术示例" not in req_body:
            errors.append("「智能体各板块任务要求」内缺少子节「各板块互动话术示例」")
        if "所给图片" not in req_body:
            errors.append("「智能体各板块任务要求」中须出现「所给图片」")
        h3_count = _count_h3_in_section(req_body)
        if h3_count < 3:
            errors.append(
                "「智能体各板块任务要求」下至少应有 2 个实训板块（`### …`）及「各板块互动话术示例」子节"
            )
        if "|" not in req_body or "智能体" not in req_body:
            errors.append("互动话术示例建议使用表格并包含智能体话术列")

    eval_body = _section_text(text, "评价标准")
    if eval_body:
        target = int(TRAINING_DOC_CONFIG["target_total_score"])
        score_sum = _parse_score_sum_from_evaluation(eval_body)
        if score_sum is not None and score_sum != target:
            errors.append(f"评价标准分项分值合计为 {score_sum}，应为 {target}")
        if "100" not in eval_body:
            errors.append("评价标准中应明确总分100分")

    return len(errors) == 0, errors
