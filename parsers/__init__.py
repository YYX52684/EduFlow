"""
文件解析器模块
支持 Markdown、DOCX、DOC、PDF 格式的文件解析
任务元数据提取：任务名称、描述、评价项（支持 .md / .docx / .doc / .txt）
"""
from .md_parser import parse_markdown
from .docx_parser import parse_docx, parse_docx_with_structure
from .doc_parser import parse_doc, parse_doc_with_structure
from .pdf_parser import parse_pdf
from .task_extractor import (
    extract_task_meta_from_doc,
    extract_task_meta_from_content_structure,
    extract_task_name_from_doc,
    extract_description_from_doc,
    extract_evaluation_items_from_doc,
)

# 支持的扩展名（统一用于解析器选择）
SUPPORTED_SCRIPT_EXTENSIONS = (".md", ".docx", ".doc", ".pdf")


def get_parser_for_extension(ext: str):
    """
    根据扩展名返回解析器函数。调用方式: parser(path) -> str（纯文本内容）。
    ext 如 ".md", ".docx", ".doc", ".pdf"。
    """
    ext = (ext or "").lower()
    if ext not in SUPPORTED_SCRIPT_EXTENSIONS:
        raise ValueError(f"不支持的文件格式: {ext}。支持: .md / .docx / .doc / .pdf")
    if ext == ".md":
        return parse_markdown
    if ext == ".docx":
        return lambda path: parse_docx_with_structure(path)[0]
    if ext == ".doc":
        return lambda path: parse_doc_with_structure(path)[0]
    if ext == ".pdf":
        return parse_pdf
    raise ValueError(f"不支持的文件格式: {ext}")


__all__ = [
    "parse_markdown",
    "parse_docx",
    "parse_docx_with_structure",
    "parse_doc",
    "parse_doc_with_structure",
    "parse_pdf",
    "SUPPORTED_SCRIPT_EXTENSIONS",
    "get_parser_for_extension",
    "extract_task_meta_from_doc",
    "extract_task_meta_from_content_structure",
    "extract_task_name_from_doc",
    "extract_description_from_doc",
    "extract_evaluation_items_from_doc",
]
