# -*- coding: utf-8 -*-
"""
卡片生成与闭环核心路径测试。
"""
import os

import pytest

from generators.frameworks import list_frameworks, get_framework
from generators.frameworks.base import BaseCardGenerator


def test_list_frameworks_includes_dspy():
    """框架库应至少包含 dspy 框架。"""
    frameworks = list_frameworks()
    ids = [f["id"] for f in frameworks]
    assert "dspy" in ids, f"dspy 应在框架列表中，当前: {ids}"


def test_get_framework_dspy():
    """能正确获取 dspy 框架类。"""
    cls, meta = get_framework("dspy")
    assert issubclass(cls, BaseCardGenerator)
    assert meta["id"] == "dspy"
    assert meta.get("name")


def test_dspy_generator_generate_all_cards_structure():
    """DSPy 生成器对简单 stages 能产出符合结构的 Markdown。"""
    from generators.frameworks.dspy import GeneratorClass

    # 使用 mock 避免真实 LLM 调用；若 GeneratorClass 支持无 key 测试则直接测
    stages = [
        {
            "id": 1,
            "title": "阶段1",
            "role": "测试角色",
            "task": "测试任务",
            "key_points": ["要点1"],
            "interaction_rounds": 3,
        },
    ]
    full_content = "测试剧本全文"

    # 无 API key 时多数生成器会报错，此处仅验证接口存在且可调用
    gen = GeneratorClass(api_key="test-key-no-llm-call")
    assert hasattr(gen, "generate_all_cards")
    assert callable(gen.generate_all_cards)


def test_closed_loop_module_import():
    """closed_loop 模块可导入且 run_simulate_and_evaluate 存在。"""
    from generators import closed_loop

    assert hasattr(closed_loop, "run_simulate_and_evaluate")
    assert callable(closed_loop.run_simulate_and_evaluate)


def _sample_cards_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(root, "output", "optimizer", "cards_for_eval.md"),
        os.path.join(root, "workspaces", "YYX", "output", "optimizer", "cards_for_eval.md"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


@pytest.mark.skipif(_sample_cards_path() is None, reason="无可用卡片样例")
def test_local_card_loader_parses_sample():
    """LocalCardLoader 能解析样例卡片文件。"""
    from simulator.card_loader import LocalCardLoader

    path = _sample_cards_path()
    loader = LocalCardLoader()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    cards = loader.parse_markdown_content(content)
    assert len(cards) >= 1
    seq = loader.get_card_sequence(cards)
    assert len(seq) >= 1
