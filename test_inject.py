#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试卡片注入功能
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_platform.card_injector import CardInjector, ParsedCard
from api_platform.api_client import PlatformAPIClient
from config import PLATFORM_CONFIG, PLATFORM_ENDPOINTS


def test_markdown_parsing():
    """测试Markdown解析功能"""
    print("=" * 60)
    print("测试 1: Markdown解析功能")
    print("=" * 60)
    
    # 使用已有的输出文件进行测试
    test_file = os.path.join(
        os.path.dirname(__file__), 
        "output", 
        "cards_output_20260131_135636.md"
    )
    
    if not os.path.exists(test_file):
        print(f"[跳过] 测试文件不存在: {test_file}")
        return False
    
    try:
        # 创建一个mock客户端（不需要实际连接）
        mock_config = {
            "base_url": "http://localhost",
            "cookie": "",
            "course_id": "test",
            "project_id": "test"
        }
        client = PlatformAPIClient(mock_config)
        injector = CardInjector(client)
        
        # 解析Markdown
        cards = injector.parse_markdown(test_file)
        
        print(f"\n[成功] 解析完成，共 {len(cards)} 张卡片")
        
        # 显示卡片摘要
        for card in cards:
            print(f"\n  卡片 {card.card_id}:")
            print(f"    - 阶段: {card.stage_num}")
            print(f"    - 类型: {card.card_type}")
            print(f"    - Role: {'有' if card.role else '无'} ({len(card.role)} 字符)")
            print(f"    - Context: {'有' if card.context else '无'} ({len(card.context)} 字符)")
            print(f"    - 知识点: {len(card.knowledge_points)} 个")
        
        # 验证卡片
        issues = injector.validate_cards(cards)
        if issues:
            print("\n[警告] 验证发现问题:")
            for issue in issues:
                print(f"  卡片 {issue['card_id']}: {issue['issues']}")
        else:
            print("\n[成功] 所有卡片验证通过")
        
        return True
        
    except Exception as e:
        print(f"\n[失败] 解析错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_platform_format_conversion():
    """测试平台格式转换"""
    print("\n" + "=" * 60)
    print("测试 2: 平台格式转换（智慧树API格式）")
    print("=" * 60)
    
    # 创建测试卡片
    card = ParsedCard(
        card_id="1A",
        stage_num=1,
        card_type="A",
        title="卡片1A",
        full_content="# 卡片1A\n\n# Role\n你是一个测试角色\n\n# Context\n测试上下文",
        role="你是一个测试角色",
        context="测试上下文",
        interaction_logic="测试交互逻辑",
        knowledge_points=["知识点1", "知识点2"]
    )
    
    # 转换为平台格式
    platform_data = card.to_platform_format(
        course_id="course123",
        train_task_id="task456"
    )
    
    print("\n转换结果:")
    for key, value in platform_data.items():
        if isinstance(value, str) and len(value) > 50:
            value = value[:50] + "..."
        elif isinstance(value, (dict, list)):
            value = str(value)[:50] + "..." if len(str(value)) > 50 else value
        print(f"  {key}: {value}")
    
    # 验证智慧树API必要字段
    required_fields = ["stepName", "llmPrompt", "nodeType"]
    missing = [f for f in required_fields if f not in platform_data]
    
    if missing:
        print(f"\n[失败] 缺少必要字段: {missing}")
        return False
    
    # 验证llmPrompt不包含卡片标题行
    if platform_data.get("llmPrompt", "").startswith("# 卡片"):
        print("\n[失败] llmPrompt不应包含卡片标题行")
        return False
    
    print("\n[成功] 格式转换正确（符合智慧树API规范）")
    return True


def test_api_client_creation():
    """测试API客户端创建"""
    print("\n" + "=" * 60)
    print("测试 3: API客户端创建")
    print("=" * 60)
    
    try:
        client = PlatformAPIClient(PLATFORM_CONFIG)
        client.set_endpoints(PLATFORM_ENDPOINTS)
        
        print(f"\n  基础URL: {client.base_url}")
        print(f"  课程ID: {client.course_id or '(未配置)'}")
        print(f"  项目ID: {client.project_id or '(未配置)'}")
        print(f"  Cookie: {'已配置' if PLATFORM_CONFIG.get('cookie') else '未配置'}")
        
        print("\n  API端点:")
        for name, endpoint in client.endpoints.items():
            print(f"    - {name}: {endpoint}")
        
        print("\n[成功] API客户端创建成功")
        return True
        
    except Exception as e:
        print(f"\n[失败] 创建错误: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("EduFlow 卡片注入功能测试")
    print("=" * 60 + "\n")
    
    results = []
    
    # 运行测试
    results.append(("Markdown解析", test_markdown_parsing()))
    results.append(("格式转换", test_platform_format_conversion()))
    results.append(("API客户端", test_api_client_creation()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    failed = len(results) - passed
    
    for name, result in results:
        status = "通过" if result else "失败"
        print(f"  [{status}] {name}")
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
