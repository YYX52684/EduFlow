# -*- coding: utf-8 -*-
"""
.doc（Word 97-2003）文件解析
通过 doc2docx 转为 .docx 后复用 docx 解析。需安装: pip install doc2docx
Windows/macOS 上 doc2docx 依赖已安装的 Microsoft Word。
"""
import os
import tempfile
from typing import Tuple, List, Dict, Any

try:
    from doc2docx import convert as doc2docx_convert
    DOC2DOCX_AVAILABLE = True
except ImportError:
    DOC2DOCX_AVAILABLE = False

from .docx_parser import parse_docx_with_structure


def parse_doc_with_structure(file_path: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    解析 .doc 文件，返回 (全文, 结构)。
    内部先转为临时 .docx，再调用 parse_docx_with_structure。
    """
    if not DOC2DOCX_AVAILABLE:
        raise ImportError(
            "解析 .doc 需要安装 doc2docx: pip install doc2docx。"
            "Windows/macOS 上需已安装 Microsoft Word。也可将文件另存为 .docx 后使用。"
        )
    path = os.path.abspath(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext != ".doc":
        raise ValueError(f"不是 .doc 文件: {path}")
    fd, docx_path = tempfile.mkstemp(suffix=".docx")
    try:
        os.close(fd)
        doc2docx_convert(path, docx_path)
        return parse_docx_with_structure(docx_path)
    finally:
        try:
            os.unlink(docx_path)
        except Exception:
            pass


def parse_doc(file_path: str) -> str:
    """解析 .doc 文件，仅返回文本内容。"""
    content, _ = parse_doc_with_structure(file_path)
    return content
