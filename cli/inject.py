# -*- coding: utf-8 -*-
"""CLI 注入：将卡片 Markdown 注入到智慧树平台（含预览）。"""
import os
import sys

from api_platform import CardInjector
from cli.common import check_platform_config, create_platform_client, progress_callback


def inject_cards_to_platform(
    md_path: str,
    task_name: str = None,
    description: str = None,
    preview_only: bool = False,
    verbose: bool = False,
) -> bool:
    """将 Markdown 卡片注入到平台；preview_only 时仅预览。返回是否成功。"""
    print("\n" + "=" * 60)
    print("智慧树平台卡片注入")
    print("=" * 60)
    if not preview_only and not check_platform_config():
        print("\n[错误] 平台配置不完整，无法注入")
        print("提示: 使用 --preview-inject 可以预览解析结果")
        return False
    try:
        client = create_platform_client()
        injector = CardInjector(client)
        if preview_only:
            print("\n[预览模式] 不会实际注入到平台\n")
            injector.preview_cards(md_path)
            return True
        print(f"\n源文件: {md_path}")
        if task_name:
            print(f"任务名称: {task_name}")
        print("正在注入卡片到平台...\n")

        def inject_progress(current: int, total: int, message: str):
            progress_callback(current, total, message)

        result = injector.inject_with_config(
            md_path,
            task_name=task_name,
            description=description,
            progress_callback=inject_progress,
        )
        print("\n" + "-" * 40)
        print("注入结果:")
        print(f"  A类卡片（节点）: {result['successful_a_cards']}/{result['total_a_cards']} 成功")
        print(f"  B类卡片（连线）: {result['successful_b_cards']}/{result['total_b_cards']} 成功")
        if result.get("evaluation_items_count") is not None:
            print(f"  评价项: {result['evaluation_items_count']} 个，总分 {result.get('total_score', 0)}")
        if verbose:
            print("\nA类卡片详情:")
            for i, card in enumerate(result["a_cards"]):
                step_id = result["step_ids"][i] if i < len(result["step_ids"]) else None
                status = "✓" if step_id else "✗"
                print(f"  [{status}] {card['card_id']} - {card['title']}")
                if step_id:
                    print(f"       节点ID: {step_id[:20]}...")
            print("\nB类卡片详情:")
            for i, card in enumerate(result["b_cards"]):
                flow_id = result["flow_ids"][i] if i < len(result["flow_ids"]) else None
                status = "✓" if flow_id else "✗"
                print(f"  [{status}] {card['card_id']} - {card['title']}")
                if flow_id:
                    print(f"       连线ID: {flow_id[:20]}...")
        print("=" * 60)
        expected_b = result["total_a_cards"] - 1
        a_ok = result["successful_a_cards"] == result["total_a_cards"]
        b_ok = result["successful_b_cards"] >= expected_b
        return a_ok and b_ok
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"\n[错误] {e}")
        return False
    except Exception as e:
        print(f"\n[错误] 注入失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def run_inject_only(md_path: str, preview_only: bool = False, verbose: bool = False):
    """仅注入模式：校验路径后调用 inject_cards_to_platform，失败则 sys.exit(1)。"""
    md_path = os.path.abspath(md_path)
    if not os.path.exists(md_path):
        print(f"错误: 文件不存在: {md_path}")
        sys.exit(1)
    print("=" * 60)
    print("教学卡片注入工具 (仅注入模式)")
    print("=" * 60)
    success = inject_cards_to_platform(md_path, preview_only=preview_only, verbose=verbose)
    if success:
        print("\n[完成] 注入成功!")
    else:
        print("\n[失败] 注入过程中出现错误")
        sys.exit(1)
