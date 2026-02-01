"""
PDF 文件解析器
使用 pdfplumber 库提取PDF文档的文本内容
"""
import os
from typing import Optional

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


def parse_pdf(file_path: str) -> str:
    """
    解析PDF文件，返回文本内容
    
    Args:
        file_path: PDF文件的路径
        
    Returns:
        文件的文本内容
        
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件格式不正确
        ImportError: pdfplumber库未安装
    """
    if not PDF_AVAILABLE:
        raise ImportError("请先安装pdfplumber库: pip install pdfplumber")
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    if not file_path.lower().endswith('.pdf'):
        raise ValueError(f"不是PDF文件: {file_path}")
    
    try:
        with pdfplumber.open(file_path) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text.strip())
            
            return '\n\n'.join(pages_text)
    except Exception as e:
        raise ValueError(f"解析PDF文件时出错: {e}")


def parse_pdf_with_pages(file_path: str) -> list[dict]:
    """
    解析PDF文件，返回每页的文本内容
    
    Args:
        file_path: PDF文件的路径
        
    Returns:
        页面列表，每个页面包含页码和文本内容
    """
    if not PDF_AVAILABLE:
        raise ImportError("请先安装pdfplumber库: pip install pdfplumber")
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    pages = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            pages.append({
                "page_number": i,
                "content": text.strip() if text else ""
            })
    
    return pages


def extract_tables(file_path: str) -> list[list[list[str]]]:
    """
    从PDF文件中提取所有表格
    
    Args:
        file_path: PDF文件的路径
        
    Returns:
        表格列表，每个表格是一个二维数组
    """
    if not PDF_AVAILABLE:
        raise ImportError("请先安装pdfplumber库: pip install pdfplumber")
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    all_tables = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                all_tables.extend(tables)
    
    return all_tables
