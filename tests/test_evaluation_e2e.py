# -*- coding: utf-8 -*-
"""
评价系统端到端：任务元数据提取、评价项 Markdown 生成、注入器解析评价项。
"""
import os

import pytest


def test_build_evaluation_markdown():
    """评价项章节可自动生成。"""
    from generators.evaluation_section import build_evaluation_markdown

    stages = [
        {"id": 1, "title": "阶段1", "task": "任务1", "key_points": ["要点1"]},
        {"id": 2, "title": "阶段2", "task": "任务2", "key_points": []},
    ]
    md = build_evaluation_markdown([], stages, 100, True)
    assert "## 评价项" in md
    assert "### 评价项1" in md
    assert "**满分值**" in md


def test_parse_evaluation_items():
    """注入器能解析 ## 评价项 章节。"""
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


def _has_task_extractor_input():
    root = os.path.join(os.path.dirname(__file__), "..")
    return os.path.exists(os.path.join(root, "input", "示例剧本.md")) or os.path.exists(
        os.path.join(root, "input", "屈原圆桌论坛.md")
    )


@pytest.mark.skipif(not _has_task_extractor_input(), reason="需要 input/示例剧本.md 或 屈原圆桌论坛.md")
def test_task_extractor():
    """从输入文档提取任务名称、描述、评价项。"""
    from parsers import extract_task_meta_from_doc

    root = os.path.join(os.path.dirname(__file__), "..")
    path = os.path.join(root, "input", "示例剧本.md")
    if not os.path.exists(path):
        path = os.path.join(root, "input", "屈原圆桌论坛.md")
    assert os.path.exists(path), "测试数据缺失"
    meta = extract_task_meta_from_doc(path)
    assert "task_name" in meta and "description" in meta and "evaluation_items" in meta
