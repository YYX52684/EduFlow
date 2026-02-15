# -*- coding: utf-8 -*-
"""
卡片注入相关测试：ParsedCard 转 A 类格式、API 客户端参数、Markdown 解析（需样例文件时跳过）。
"""
import os

import pytest

from api_platform.card_injector import CardInjector, ParsedCard
from api_platform.api_client import PlatformAPIClient
from config import PLATFORM_CONFIG, PLATFORM_ENDPOINTS


def test_parsed_card_to_a_format():
    """ParsedCard 转 A 类平台格式包含必要字段且不含卡片标题行。"""
    card = ParsedCard(
        card_id="1A",
        stage_num=1,
        card_type="A",
        title="卡片1A",
        full_content="# 卡片1A\n\n# Role\n你是一个测试角色\n\n# Context\n测试上下文",
        role="你是一个测试角色",
        context="测试上下文",
        interaction_logic="测试交互逻辑",
        knowledge_points=["知识点1", "知识点2"],
    )
    platform_data = card.to_a_card_format()
    assert "step_name" in platform_data
    assert "llm_prompt" in platform_data
    assert "description" in platform_data
    # llm_prompt 不应保留卡片标题行
    assert not (platform_data.get("llm_prompt") or "").strip().startswith("# 卡片")


def test_api_client_creation():
    """API 客户端能使用全局配置创建并设置端点。"""
    client = PlatformAPIClient(PLATFORM_CONFIG)
    client.set_endpoints(PLATFORM_ENDPOINTS)
    assert hasattr(client, "base_url")
    assert hasattr(client, "endpoints")
    assert "create_step" in client.endpoints


def _sample_cards_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(root, "output", "cards_output_20260131_135636.md"),
        os.path.join(root, "workspaces", "编译原理管理", "output", "cards_for_eval.md"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


@pytest.mark.skipif(_sample_cards_path() is None, reason="无可用卡片 Markdown 样例文件")
def test_markdown_parsing():
    """解析真实卡片 Markdown 文件并验证基本结构。"""
    path = _sample_cards_path()
    mock_config = {
        "base_url": "http://localhost",
        "cookie": "",
        "course_id": "test",
        "train_task_id": "test",
    }
    client = PlatformAPIClient(mock_config)
    injector = CardInjector(client)
    cards = injector.parse_markdown(path)
    assert len(cards) >= 1
    for card in cards:
        assert card.card_id
        assert card.stage_num >= 1
        assert card.card_type in ("A", "B")
    issues = injector.validate_cards(cards)
    assert isinstance(issues, list)
