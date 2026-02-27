# -*- coding: utf-8 -*-
"""
卡片配置流测试：CARD_DEFAULTS、阶段元数据、ParsedCard 格式、ContentSplitter 字段。
"""
import json
import re
import inspect

import pytest

from config import CARD_DEFAULTS


def test_card_defaults():
    """CARD_DEFAULTS 应包含抓包确认的字段名。"""
    required_keys = [
        "model_id",
        "history_num",
        "trainer_name",
        "default_interaction_rounds",
    ]
    for key in required_keys:
        assert key in CARD_DEFAULTS, f"缺少 {key}"


def test_stage_meta_generation():
    """阶段元数据生成格式正确（STAGE_META 注释 + JSON）。"""
    from generators.dspy_card_generator import DSPyCardGenerator

    stage = {
        "id": 1,
        "title": "Test Stage",
        "description": "This is a test stage description",
        "interaction_rounds": 7,
        "role": "Test Role",
        "task": "Complete test task",
        "key_points": ["Point1", "Point2"],
        "content_excerpt": "Test excerpt",
    }

    generator = DSPyCardGenerator(api_key="test-key-for-unit-test")
    meta_str = generator._create_stage_meta(stage)
    meta_pattern = r"<!--\s*STAGE_META:\s*(\{.*?\})\s*-->"
    match = re.search(meta_pattern, meta_str)
    assert match, "应包含 STAGE_META 注释"
    meta_data = json.loads(match.group(1))
    assert meta_data.get("stage_name")
    assert meta_data.get("description")
    assert meta_data.get("interaction_rounds") == 7


def test_stage_meta_parsing():
    """注入器能正确解析 STAGE_META。"""
    from api_platform.card_injector import CardInjector

    class MockAPIClient:
        pass

    injector = CardInjector(MockAPIClient())
    test_content = """# Card 1A

<!-- STAGE_META: {"stage_name": "Initial Assessment", "description": "Initial patient assessment", "interaction_rounds": 6} -->

# Role
You are patient Zhang...
"""
    meta = injector._extract_stage_meta(test_content)
    assert meta is not None
    assert meta.get("stage_name") == "Initial Assessment"
    assert meta.get("interaction_rounds") == 6


def test_parsed_card_to_a_card_format():
    """ParsedCard.to_a_card_format 合并 LLM 字段与配置默认值。"""
    from api_platform.card_injector import ParsedCard

    card = ParsedCard(
        card_id="1A",
        stage_num=1,
        card_type="A",
        title="Test Card",
        full_content="Test content",
        stage_name="LLM Stage Name",
        stage_description="LLM Description",
        interaction_rounds=8,
    )
    result = card.to_a_card_format()
    assert result["step_name"] == "LLM Stage Name"
    assert result["description"] == "LLM Description"
    assert result["interaction_rounds"] == 8
    assert "model_id" in result or "model_id" in str(result)
    assert result.get("trainer_name") is not None


def test_api_client_create_step_params():
    """PlatformAPIClient.create_step 参数与抓包字段一致。"""
    from api_platform.api_client import PlatformAPIClient

    sig = inspect.signature(PlatformAPIClient.create_step)
    params = list(sig.parameters.keys())
    required = [
        "step_name",
        "llm_prompt",
        "description",
        "interaction_rounds",
        "model_id",
        "history_num",
        "trainer_name",
    ]
    for param in required:
        assert param in params, f"缺少参数 {param}"


def test_content_splitter_prompt_fields():
    """ContentSplitter.SPLIT_PROMPT 包含 description、interaction_rounds。"""
    from generators.content_splitter import ContentSplitter

    prompt = ContentSplitter.SPLIT_PROMPT
    assert "description" in prompt
    assert "interaction_rounds" in prompt
