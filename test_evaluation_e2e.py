#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
端到端测试：任务元数据提取、评价项 Markdown 生成、注入器解析
不依赖真实平台 API，可在项目根目录运行: python test_evaluation_e2e.py
"""
import os
import sys

# 项目根目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_task_extractor():
    """从输入文档提取任务名称、描述、评价项"""
    from parsers import extract_task_meta_from_doc

    input_dir = os.path.join(os.path.dirname(__file__), "input")
    path = os.path.join(input_dir, "示例剧本.md")
    if not os.path.exists(path):
        path = os.path.join(input_dir, "屈原圆桌论坛.md")
    if not os.path.exists(path):
        print("  [跳过] 未找到 input/示例剧本.md 或 屈原圆桌论坛.md")
        return False

    meta = extract_task_meta_from_doc(path)
    assert "task_name" in meta and "description" in meta and "evaluation_items" in meta
    print(f"  task_name: {meta['task_name'][:40]}...")
    print(f"  description 长度: {len(meta['description'])}")
    print(f"  evaluation_items: {len(meta['evaluation_items'])} 个")
    return True


def test_build_evaluation_markdown():
    """评价项章节自动生成"""
    from generators.evaluation_section import build_evaluation_markdown

    stages = [
        {"id": 1, "title": "阶段1", "task": "任务1", "key_points": ["要点1"]},
        {"id": 2, "title": "阶段2", "task": "任务2", "key_points": []},
    ]
    md = build_evaluation_markdown([], stages, 100, True)
    assert "## 评价项" in md
    assert "### 评价项1" in md
    assert "**满分值**" in md
    print("  build_evaluation_markdown: OK")
    return True


def test_parse_evaluation_items():
    """注入器解析 ## 评价项 章节"""
    from api_platform.card_injector import CardInjector

    class FakeClient:
        pass

    injector = CardInjector(FakeClient())
    sample = """
## 评价项

### 评价项1：项目定位与市场分析
- **满分值**: 20
- **评价描述**: 考察学生对农业创业项目的市场定位准确性
- **详细要求**: 能够清晰阐述目标市场、竞争优势

### 评价项2：商业模式设计
- **满分值**: 25
- **评价描述**: 考察商业模式设计
- **详细要求**: 能够说明盈利方式
"""
    items = injector.parse_evaluation_items(sample)
    assert len(items) >= 2
    assert items[0].get("item_name") and items[0].get("score") == 20
    assert items[1].get("score") == 25
    print(f"  parse_evaluation_items: {len(items)} 个评价项, 首项分值={items[0].get('score')}")
    return True


def main():
    print("=" * 50)
    print("评价系统端到端测试")
    print("=" * 50)
    ok = 0
    ok += test_task_extractor()
    ok += test_build_evaluation_markdown()
    ok += test_parse_evaluation_items()
    print("=" * 50)
    print(f"通过: {ok}/3")
    print("=" * 50)
    return 0 if ok == 3 else 1


if __name__ == "__main__":
    sys.exit(main())
