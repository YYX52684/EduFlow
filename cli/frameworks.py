# -*- coding: utf-8 -*-
"""CLI 生成框架：列出可用框架。"""
from generators import list_frameworks


def run_list_frameworks():
    """列出框架库中所有可用生成框架并打印。"""
    frameworks = list_frameworks()
    if not frameworks:
        print("框架库中暂无可用生成框架。请在 generators/frameworks/ 下添加框架。")
        return
    print("可用生成框架:")
    print("-" * 50)
    for i, m in enumerate(frameworks, 1):
        print(f"  {i}. {m['id']} - {m['name']}")
        if m.get("description"):
            print(f"     {m['description']}")
    print("-" * 50)
