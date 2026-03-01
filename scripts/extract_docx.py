# -*- coding: utf-8 -*-
"""临时脚本：从指定 docx 提取全文并写入 txt，便于查看与优化。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from parsers.docx_parser import parse_docx_with_structure

def main():
    path = r"c:\Users\俞宇星\OneDrive\文档\WXWork\1688854982805196\Cache\File\2026-02\实训任务文档 - 第十章.docx"
    if not os.path.exists(path):
        print("File not found:", path)
        return
    content, structure = parse_docx_with_structure(path)
    out = os.path.join(os.path.dirname(__file__), "实训任务文档_第十章_原文.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    print("Written:", out)
    print("--- CONTENT (first 8000 chars) ---")
    print(content[:8000])
    if len(content) > 8000:
        print("\n... [truncated] ...")

if __name__ == "__main__":
    main()
