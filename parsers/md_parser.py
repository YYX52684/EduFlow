"""
Markdown 文件解析器
直接读取并返回Markdown文件的文本内容
"""
import os
from typing import Optional


def parse_markdown(file_path: str, encoding: str = "utf-8") -> str:
    """
    解析Markdown文件，返回文本内容
    
    Args:
        file_path: Markdown文件的路径
        encoding: 文件编码，默认为utf-8
        
    Returns:
        文件的文本内容
        
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件格式不正确
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    if not file_path.lower().endswith('.md'):
        raise ValueError(f"不是Markdown文件: {file_path}")
    
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()
        return content.strip()
    except UnicodeDecodeError:
        # 尝试其他常见编码
        for alt_encoding in ['gbk', 'gb2312', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=alt_encoding) as f:
                    content = f.read()
                return content.strip()
            except UnicodeDecodeError:
                continue
        raise ValueError(f"无法解码文件: {file_path}")


def extract_sections(content: str) -> list[dict]:
    """
    从Markdown内容中提取各个章节
    
    Args:
        content: Markdown文本内容
        
    Returns:
        章节列表，每个章节包含标题和内容
    """
    lines = content.split('\n')
    sections = []
    current_section = {"title": "", "level": 0, "content": []}
    
    for line in lines:
        # 检测标题行
        if line.startswith('#'):
            # 保存之前的章节
            if current_section["title"] or current_section["content"]:
                current_section["content"] = '\n'.join(current_section["content"]).strip()
                sections.append(current_section)
            
            # 计算标题级别
            level = len(line) - len(line.lstrip('#'))
            title = line.lstrip('#').strip()
            current_section = {"title": title, "level": level, "content": []}
        else:
            current_section["content"].append(line)
    
    # 保存最后一个章节
    if current_section["title"] or current_section["content"]:
        current_section["content"] = '\n'.join(current_section["content"]).strip()
        sections.append(current_section)
    
    return sections
