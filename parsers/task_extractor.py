"""
从输入文档中提取任务元数据：任务名称、描述、评价项
支持 .md、.docx、.txt 格式
"""
import os
import re
from typing import List, Dict, Any, Optional

from .md_parser import parse_markdown, extract_sections
from .docx_parser import parse_docx, extract_structure, parse_docx_with_structure
try:
    from .pdf_parser import parse_pdf
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False

# 评价相关章节关键词
EVALUATION_KEYWORDS = ("评价", "评分", "考核", "评分标准", "评价标准", "考核要点")


def _read_txt(path: str) -> str:
    """读取 .txt 文件内容"""
    encodings = ["utf-8", "gbk", "gb2312"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read().strip()
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法解码文件: {path}")


def _structure_from_txt(content: str) -> List[Dict[str, Any]]:
    """
    从纯文本中推断章节结构
    识别：# 标题、第X章、一、二、或 1. 2. 等
    """
    structure = []
    lines = content.split("\n")
    current = {"title": "", "level": 1, "content": []}

    for line in lines:
        stripped = line.strip()
        # 一级标题：# xxx 或 ## xxx
        m_hash = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        # 第X章、一、二、
        m_chapter = re.match(r"^(第[一二三四五六七八九十百千\d]+[章节目部分])\s*(.*)$", stripped)
        m_num = re.match(r"^([一二三四五六七八九十]+|[\d]+)[、.]\s*(.+)$", stripped)

        if m_hash:
            if current["title"] or current["content"]:
                current["content"] = "\n".join(current["content"]).strip()
                structure.append(current)
            level = len(m_hash.group(1))
            current = {"title": m_hash.group(2).strip(), "level": level, "content": []}
        elif m_chapter:
            if current["title"] or current["content"]:
                current["content"] = "\n".join(current["content"]).strip()
                structure.append(current)
            title = m_chapter.group(1)
            if m_chapter.group(2):
                title = title + " " + m_chapter.group(2).strip()
            current = {"title": title, "level": 1, "content": []}
        elif m_num and len(stripped) < 80:
            if current["title"] or current["content"]:
                current["content"] = "\n".join(current["content"]).strip()
                structure.append(current)
            current = {"title": stripped, "level": 2, "content": []}
        else:
            current["content"].append(line)

    if current["title"] or current["content"]:
        current["content"] = "\n".join(current["content"]).strip()
        structure.append(current)
    return structure


def _structure_from_md(content: str) -> List[Dict[str, Any]]:
    """将 md_parser.extract_sections 的格式转为统一 structure 格式"""
    sections = extract_sections(content)
    return [
        {"title": s["title"], "level": s["level"], "content": s.get("content", "")}
        for s in sections
    ]


def _get_content_and_structure(file_path: str) -> tuple:
    """
    根据文件类型获取原始内容和章节结构
    Returns:
        (content: str, structure: List[dict]) 每个 dict 含 title, level, content
    """
    path = os.path.abspath(file_path)
    ext = os.path.splitext(path)[1].lower()

    if ext == ".md":
        content = parse_markdown(path)
        structure = _structure_from_md(content)
        return content, structure
    if ext == ".docx":
        content, raw = parse_docx_with_structure(path)
        structure = [
            {"title": s["title"], "level": s.get("level", 1), "content": s.get("content", "")}
            for s in raw
        ]
        return content, structure
    if ext == ".txt":
        content = _read_txt(path)
        structure = _structure_from_txt(content)
        return content, structure
    if ext == ".pdf" and _PDF_AVAILABLE:
        content = parse_pdf(path)
        structure = _structure_from_txt(content)
        return content, structure

    raise ValueError(f"不支持的任务元数据提取格式: {ext}，支持 .md / .docx / .txt / .pdf")


def _is_evaluation_section(title: str) -> bool:
    """判断章节标题是否为评价/考核相关"""
    return any(kw in title for kw in EVALUATION_KEYWORDS)


def _parse_evaluation_items_from_content(section_content: str) -> List[Dict[str, Any]]:
    """
    从一段文本中解析评价项
    支持格式：
    - ### 评价项1：xxx 或 ### 1. xxx
    - **满分值**: 20 / **分值**: 20 / 满分值：20
    - **评价描述**: xxx / **详细要求**: xxx
    - 1. xxx（20分）
    """
    items = []
    if not section_content or not section_content.strip():
        return items

    # 按 ### 评价项 或 ### N. 或 **评价项 分块
    blocks = re.split(
        r"(?=###\s*评价项\d*[：:]\s*|###\s*\d+[.．、]\s*|\*\*评价项\d*[：:]\s*)",
        section_content,
        flags=re.IGNORECASE,
    )

    for block in blocks:
        block = block.strip()
        if not block or len(block) < 5:
            continue

        # 去掉块开头的 ### 评价项N： 或 ### N.
        block = re.sub(r"^###\s*评价项\d*[：:]\s*", "", block)
        block = re.sub(r"^###\s*\d+[.．、]\s*", "", block)
        block = re.sub(r"^\*\*评价项\d*[：:]\s*", "", block)

        name = ""
        score = 0
        description = ""
        require_detail = ""

        # 第一行常为名称（或名称+分值）
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if lines:
            first = lines[0]
            # 如 "项目定位与市场分析（20分）"
            m = re.search(r"^(.+?)\s*[（(](\d+)\s*分[）)]\s*$", first)
            if m:
                name = m.group(1).strip()
                score = int(m.group(2))
            else:
                name = first
            rest = "\n".join(lines[1:])
        else:
            rest = block

        # 从 rest 中提取 **满分值** / **分值** / **评价描述** / **详细要求**
        score_m = re.search(r"\*\*(?:满分值|分值|分数)\s*[：:]\s*\*\*?\s*(\d+)", rest, re.IGNORECASE)
        if score_m and score == 0:
            score = int(score_m.group(1))
        if not name:
            name_m = re.search(r"^[#*]*\s*(.+?)(?:\s*[（(]\d+\s*分[）)]|\s*$)", block, re.DOTALL)
            if name_m:
                name = name_m.group(1).strip().split("\n")[0][:80]

        desc_m = re.search(r"\*\*(?:评价描述|描述)\s*[：:]\s*\*\*?\s*([^\n*]+(?:\n(?!\*\*)[^\n*]*)*)", rest, re.IGNORECASE)
        if desc_m:
            description = desc_m.group(1).strip()
        req_m = re.search(r"\*\*(?:详细要求|要求)\s*[：:]\s*\*\*?\s*([^\n*]+(?:\n(?!\*\*)[^\n*]*)*)", rest, re.IGNORECASE)
        if req_m:
            require_detail = req_m.group(1).strip()
        if not description and rest and not re.match(r"^\s*\*\*", rest):
            description = rest[:500].strip()

        if name or score > 0:
            items.append({
                "item_name": name or "未命名评价项",
                "score": score,
                "description": description,
                "require_detail": require_detail,
            })

    # 若上面没解析到，尝试简单列表：1. xxx（20分）
    if not items:
        for m in re.finditer(r"(?:^|\n)\s*(?:\d+[.．、]|[-*])\s*(.+?)\s*[（(](\d+)\s*分[）)]", section_content):
            items.append({
                "item_name": m.group(1).strip(),
                "score": int(m.group(2)),
                "description": "",
                "require_detail": "",
            })

    return items


def extract_task_meta_from_content_structure(
    content: str,
    structure: List[Dict[str, Any]],
    base_name: str = "",
) -> Dict[str, Any]:
    """
    从已解析的 content 与 structure 提取任务名称、描述、评价项。
    用于避免对同一文档重复打开（如 main 流程中已用 parse_docx_with_structure 时）。

    Returns:
        同 extract_task_meta_from_doc
    """
    task_name = base_name or "未命名任务"
    description = ""
    evaluation_items: List[Dict[str, Any]] = []

    for s in structure:
        if s.get("level", 1) == 1 and s.get("title"):
            task_name = s["title"].strip()
            break

    for s in structure:
        text = (s.get("content") or "").strip()
        if not text:
            continue
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if paras:
            description = "\n\n".join(paras[:2])
            if len(description) > 800:
                description = description[:800].rstrip() + "…"
            break

    for s in structure:
        if not _is_evaluation_section(s.get("title", "")):
            continue
        section_content = s.get("content") or ""
        items = _parse_evaluation_items_from_content(section_content)
        if items:
            evaluation_items.extend(items)
            break
    if not evaluation_items and content:
        for kw in ("评价标准", "考核要点", "评分标准"):
            idx = content.find(kw)
            if idx == -1:
                continue
            chunk = content[idx : idx + 3000]
            found = _parse_evaluation_items_from_content(chunk)
            if found:
                evaluation_items = found
                break

    return {
        "task_name": task_name,
        "description": description,
        "evaluation_items": evaluation_items,
    }


def extract_task_meta_from_doc(file_path: str) -> Dict[str, Any]:
    """
    从输入文档中提取任务名称、描述、评价项

    Args:
        file_path: 输入文件路径（.md / .docx / .txt）

    Returns:
        {
            "task_name": str,
            "description": str,
            "evaluation_items": [ {"item_name", "score", "description", "require_detail"}, ... ]
        }
    """
    content, structure = _get_content_and_structure(file_path)
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    return extract_task_meta_from_content_structure(content, structure, base_name)


def extract_task_name_from_doc(file_path: str) -> str:
    """从输入文档中提取任务名称"""
    meta = extract_task_meta_from_doc(file_path)
    return meta["task_name"]


def extract_description_from_doc(file_path: str) -> str:
    """从输入文档中提取任务描述"""
    meta = extract_task_meta_from_doc(file_path)
    return meta["description"]


def extract_evaluation_items_from_doc(file_path: str) -> List[Dict[str, Any]]:
    """从输入文档中提取评价项列表"""
    meta = extract_task_meta_from_doc(file_path)
    return meta["evaluation_items"]
