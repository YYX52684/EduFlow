#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test card configuration flow
Validates the complete data flow from content_splitter to api_client
"""
import sys
import os
import io

# Force UTF-8 encoding for stdout/stderr
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CARD_DEFAULTS

def test_card_defaults():
    """Test card default config loading"""
    print("=" * 60)
    print("Test 1: Card Defaults (CARD_DEFAULTS)")
    print("=" * 60)
    
    # Keys confirmed via packet capture
    required_keys = [
        ("model_id", "modelId"),
        ("history_num", "historyRecordNum"),
        ("trainer_name", "trainerName"),
        ("default_interaction_rounds", "interactiveRounds"),
    ]
    
    for key, api_field in required_keys:
        value = CARD_DEFAULTS.get(key)
        status = "[OK]" if value is not None or value == "" else "[FAIL]"
        print(f"  {status} {key} -> {api_field}: '{value}'")
    
    print()
    return all(key in CARD_DEFAULTS for key, _ in required_keys)


def test_stage_meta_generation():
    """Test stage metadata generation"""
    print("=" * 60)
    print("Test 2: Stage Meta Generation")
    print("=" * 60)
    
    from generators.card_generator import CardGenerator
    
    # Mock stage data
    stage = {
        "id": 1,
        "title": "Test Stage",
        "description": "This is a test stage description",
        "interaction_rounds": 7,
        "role": "Test Role",
        "task": "Complete test task",
        "key_points": ["Point1", "Point2"],
        "content_excerpt": "Test excerpt"
    }
    
    # Create generator without API client
    class MockCardGenerator(CardGenerator):
        def __init__(self):
            self.card_a_template = ""
            self.card_b_template = ""
    
    generator = MockCardGenerator()
    meta_str = generator._create_stage_meta(stage)
    
    print(f"  Generated metadata:")
    print(f"  {meta_str}")
    
    # Validate metadata format
    import json
    import re
    
    meta_pattern = r'<!--\s*STAGE_META:\s*(\{.*?\})\s*-->'
    match = re.search(meta_pattern, meta_str)
    
    if match:
        meta_data = json.loads(match.group(1))
        print(f"  [OK] Metadata format correct")
        print(f"      stage_name: {meta_data.get('stage_name')}")
        print(f"      description: {meta_data.get('description')}")
        print(f"      interaction_rounds: {meta_data.get('interaction_rounds')}")
        return True
    else:
        print(f"  [FAIL] Metadata format incorrect")
        return False


def test_stage_meta_parsing():
    """Test stage metadata parsing"""
    print()
    print("=" * 60)
    print("Test 3: Stage Meta Parsing")
    print("=" * 60)
    
    from platform.card_injector import CardInjector
    
    # Mock card content with metadata
    test_content = '''# Card 1A

<!-- STAGE_META: {"stage_name": "Initial Assessment", "description": "Initial patient assessment", "interaction_rounds": 6} -->

# Role
You are patient Zhang...
'''
    
    # Create injector without real API client
    class MockAPIClient:
        pass
    
    injector = CardInjector(MockAPIClient())
    meta = injector._extract_stage_meta(test_content)
    
    if meta:
        print(f"  [OK] Metadata parsing successful")
        print(f"      stage_name: {meta.get('stage_name')}")
        print(f"      description: {meta.get('description')}")
        print(f"      interaction_rounds: {meta.get('interaction_rounds')}")
        return True
    else:
        print(f"  [FAIL] Metadata parsing failed")
        return False


def test_parsed_card_to_format():
    """Test ParsedCard.to_a_card_format output"""
    print()
    print("=" * 60)
    print("Test 4: ParsedCard.to_a_card_format Config Merge")
    print("=" * 60)
    
    from platform.card_injector import ParsedCard
    
    # Create test card with LLM-specified config
    card = ParsedCard(
        card_id="1A",
        stage_num=1,
        card_type="A",
        title="Test Card",
        full_content="Test content",
        stage_name="LLM Stage Name",
        stage_description="LLM Description",
        interaction_rounds=8  # LLM suggests 8 rounds
    )
    
    result = card.to_a_card_format()
    
    print(f"  Generated A-type card format:")
    for key, value in result.items():
        print(f"      {key}: {value}")
    
    # Verify config sources (field names confirmed via packet capture)
    checks = [
        ("step_name", "LLM Stage Name", "LLM Generated -> stepName"),
        ("description", "LLM Description", "LLM Generated -> description"),
        ("interaction_rounds", 8, "LLM Suggested -> interactiveRounds"),
        ("model_id", CARD_DEFAULTS.get("model_id"), "Config Default -> modelId"),
        ("history_num", CARD_DEFAULTS.get("history_num"), "Config Default -> historyRecordNum"),
        ("trainer_name", CARD_DEFAULTS.get("trainer_name"), "Config Default -> trainerName"),
    ]
    
    print()
    print(f"  Config source validation:")
    all_passed = True
    for key, expected, source in checks:
        actual = result.get(key)
        status = "[OK]" if actual == expected else "[FAIL]"
        if actual != expected:
            all_passed = False
            print(f"      {status} {key}: expected={expected}, actual={actual} (source: {source})")
        else:
            print(f"      {status} {key}: {actual} (source: {source})")
    
    return all_passed


def test_api_client_params():
    """Test API Client create_step method parameters"""
    print()
    print("=" * 60)
    print("Test 5: API Client create_step Parameters")
    print("=" * 60)
    
    from platform.api_client import PlatformAPIClient
    import inspect
    
    # Get create_step method parameters
    sig = inspect.signature(PlatformAPIClient.create_step)
    params = list(sig.parameters.keys())
    
    # Parameters confirmed via packet capture
    required_params = [
        ("step_name", "stepName"),
        ("llm_prompt", "llmPrompt"),
        ("description", "description"),
        ("interaction_rounds", "interactiveRounds"),
        ("model_id", "modelId"),
        ("history_num", "historyRecordNum"),
        ("trainer_name", "trainerName"),
    ]
    
    print(f"  create_step method parameter check:")
    all_present = True
    for param, api_field in required_params:
        status = "[OK]" if param in params else "[FAIL]"
        if param not in params:
            all_present = False
        print(f"      {status} {param} -> {api_field}")
    
    return all_present


def test_content_splitter_prompt():
    """Test ContentSplitter SPLIT_PROMPT contains new fields"""
    print()
    print("=" * 60)
    print("Test 6: ContentSplitter SPLIT_PROMPT Fields")
    print("=" * 60)
    
    from generators.content_splitter import ContentSplitter
    
    prompt = ContentSplitter.SPLIT_PROMPT
    
    required_fields = [
        "description",
        "interaction_rounds"
    ]
    
    print(f"  SPLIT_PROMPT field check:")
    all_present = True
    for field in required_fields:
        status = "[OK]" if field in prompt else "[FAIL]"
        if field not in prompt:
            all_present = False
        print(f"      {status} {field} in prompt")
    
    return all_present


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("Card Configuration Flow Test Suite")
    print("=" * 60 + "\n")
    
    results = []
    
    results.append(("Card Defaults", test_card_defaults()))
    results.append(("Meta Generation", test_stage_meta_generation()))
    results.append(("Meta Parsing", test_stage_meta_parsing()))
    results.append(("Config Merge", test_parsed_card_to_format()))
    results.append(("API Parameters", test_api_client_params()))
    results.append(("Splitter Fields", test_content_splitter_prompt()))
    
    print()
    print("=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    passed = 0
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} {name}")
        if result:
            passed += 1
    
    print()
    print(f"Total: {passed}/{len(results)} tests passed")
    print("=" * 60)
    
    return passed == len(results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
