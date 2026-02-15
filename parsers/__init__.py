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

__all__ = [
    "parse_markdown",
    "parse_docx",
    "parse_docx_with_structure",
    "parse_doc",
    "parse_doc_with_structure",
    "parse_pdf",
    "extract_task_meta_from_doc",
    "extract_task_meta_from_content_structure",
    "extract_task_name_from_doc",
    "extract_description_from_doc",
    "extract_evaluation_items_from_doc",
]
