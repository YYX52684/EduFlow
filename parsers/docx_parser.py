"""
DOCX 文件解析器
使用 python-docx 库提取Word文档的文本和结构
"""
import os
from typing import Optional

try:
    from docx import Document
    from docx.opc.exceptions import PackageNotFoundError
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False


def parse_docx(file_path: str) -> str:
    """
    解析DOCX文件，返回文本内容
    
    Args:
        file_path: DOCX文件的路径
        
    Returns:
        文件的文本内容
        
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件格式不正确
        ImportError: python-docx库未安装
    """
    if not DOCX_AVAILABLE:
        raise ImportError("请先安装python-docx库: pip install python-docx")
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    if not file_path.lower().endswith('.docx'):
        raise ValueError(f"不是DOCX文件: {file_path}")
    
    try:
        doc = Document(file_path)
    except PackageNotFoundError:
        raise ValueError(f"无法打开文件，可能不是有效的DOCX文件: {file_path}")
    except Exception as e:
        raise ValueError(f"解析DOCX文件时出错: {e}")
    
    # 提取所有段落文本
    paragraphs = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)
    
    # 提取表格中的文本
    for table in doc.tables:
        for row in table.rows:
            row_text = []
            for cell in row.cells:
                cell_text = cell.text.strip()
                if cell_text:
                    row_text.append(cell_text)
            if row_text:
                paragraphs.append(' | '.join(row_text))
    
    return '\n\n'.join(paragraphs)


def extract_structure(file_path: str) -> list[dict]:
    """
    从DOCX文件中提取文档结构（标题和正文）
    
    Args:
        file_path: DOCX文件的路径
        
    Returns:
        结构列表，包含标题级别和内容
    """
    if not DOCX_AVAILABLE:
        raise ImportError("请先安装python-docx库: pip install python-docx")
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    doc = Document(file_path)
    structure = []
    current_section = {"title": "", "level": 0, "content": []}
    
    for para in doc.paragraphs:
        # 检查是否是标题样式
        style_name = para.style.name if para.style else ""
        
        if style_name.startswith('Heading'):
            # 保存之前的章节
            if current_section["title"] or current_section["content"]:
                current_section["content"] = '\n'.join(current_section["content"]).strip()
                structure.append(current_section)
            
            # 提取标题级别
            try:
                level = int(style_name.replace('Heading ', '').replace('Heading', '1'))
            except ValueError:
                level = 1
            
            current_section = {
                "title": para.text.strip(),
                "level": level,
                "content": []
            }
        else:
            text = para.text.strip()
            if text:
                current_section["content"].append(text)
    
    # 保存最后一个章节
    if current_section["title"] or current_section["content"]:
        current_section["content"] = '\n'.join(current_section["content"]).strip()
        structure.append(current_section)
    
    return structure
