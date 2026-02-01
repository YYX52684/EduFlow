#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
教学卡片自动生成脚本
支持从 Markdown、DOCX、PDF 格式的教学剧本生成 A/B 类教学卡片
"""
import argparse
import os
import sys
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import INPUT_DIR, OUTPUT_DIR, PLATFORM_CONFIG, PLATFORM_ENDPOINTS
from parsers import parse_markdown, parse_docx, parse_pdf
from generators import ContentSplitter, CardGenerator
from platform import PlatformAPIClient, CardInjector


def get_parser_for_file(file_path: str):
    """
    根据文件扩展名返回对应的解析器函数
    
    Args:
        file_path: 文件路径
        
    Returns:
        解析器函数
        
    Raises:
        ValueError: 不支持的文件格式
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    parsers = {
        '.md': parse_markdown,
        '.docx': parse_docx,
        '.pdf': parse_pdf,
    }
    
    if ext not in parsers:
        raise ValueError(f"不支持的文件格式: {ext}。支持的格式: {', '.join(parsers.keys())}")
    
    return parsers[ext]


def progress_callback(current: int, total: int, message: str):
    """
    进度回调函数，显示生成进度
    
    Args:
        current: 当前进度
        total: 总数
        message: 进度消息
    """
    percentage = int(current / total * 100)
    bar_length = 30
    filled_length = int(bar_length * current / total)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    
    print(f"\r[{bar}] {percentage}% - {message}", end='', flush=True)
    
    if current == total:
        print()  # 换行


def check_platform_config() -> bool:
    """
    检查平台配置是否完整
    
    Returns:
        True如果配置完整
    """
    missing = []
    
    if not PLATFORM_CONFIG.get("cookie"):
        missing.append("PLATFORM_COOKIE")
    if not PLATFORM_CONFIG.get("authorization"):
        missing.append("PLATFORM_AUTHORIZATION")
    if not PLATFORM_CONFIG.get("course_id"):
        missing.append("PLATFORM_COURSE_ID")
    if not PLATFORM_CONFIG.get("train_task_id"):
        missing.append("PLATFORM_TRAIN_TASK_ID")
    if not PLATFORM_CONFIG.get("start_node_id"):
        missing.append("PLATFORM_START_NODE_ID (训练开始节点)")
    if not PLATFORM_CONFIG.get("end_node_id"):
        missing.append("PLATFORM_END_NODE_ID (训练结束节点)")
    
    if missing:
        print("\n[警告] 以下配置项缺失:")
        for item in missing:
            print(f"  - {item}")
        print("\n请在 .env 文件中设置这些配置")
        return False
    
    return True


def create_platform_client() -> PlatformAPIClient:
    """
    创建平台API客户端
    
    Returns:
        配置好的API客户端
    """
    client = PlatformAPIClient(PLATFORM_CONFIG)
    client.set_endpoints(PLATFORM_ENDPOINTS)
    return client


def inject_cards_to_platform(md_path: str, preview_only: bool = False, verbose: bool = False) -> bool:
    """
    将Markdown文件中的卡片注入到平台
    
    Args:
        md_path: Markdown文件路径
        preview_only: 是否仅预览
        verbose: 详细输出
        
    Returns:
        True如果成功
    """
    print("\n" + "=" * 60)
    print("智慧树平台卡片注入")
    print("=" * 60)
    
    # 检查配置
    if not preview_only and not check_platform_config():
        print("\n[错误] 平台配置不完整，无法注入")
        print("提示: 使用 --preview-inject 可以预览解析结果")
        return False
    
    try:
        # 创建客户端和注入器
        client = create_platform_client()
        injector = CardInjector(client)
        
        if preview_only:
            # 仅预览模式
            print("\n[预览模式] 不会实际注入到平台\n")
            injector.preview_cards(md_path)
            return True
        
        # 执行注入
        print(f"\n源文件: {md_path}")
        print("正在注入卡片到平台...\n")
        
        def inject_progress(current: int, total: int, message: str):
            progress_callback(current, total, message)
        
        result = injector.inject_from_file(
            md_path,
            progress_callback=inject_progress
        )
        
        # 显示结果
        print("\n" + "-" * 40)
        print("注入结果:")
        print(f"  A类卡片（节点）: {result['successful_a_cards']}/{result['total_a_cards']} 成功")
        print(f"  B类卡片（连线）: {result['successful_b_cards']}/{result['total_b_cards']} 成功")
        
        if verbose:
            print("\nA类卡片详情:")
            for i, card in enumerate(result['a_cards']):
                step_id = result['step_ids'][i] if i < len(result['step_ids']) else None
                status = "✓" if step_id else "✗"
                print(f"  [{status}] {card['card_id']} - {card['title']}")
                if step_id:
                    print(f"       节点ID: {step_id[:20]}...")
            
            print("\nB类卡片详情:")
            for i, card in enumerate(result['b_cards']):
                flow_id = result['flow_ids'][i] if i < len(result['flow_ids']) else None
                status = "✓" if flow_id else "✗"
                print(f"  [{status}] {card['card_id']} - {card['title']}")
                if flow_id:
                    print(f"       连线ID: {flow_id[:20]}...")
        
        print("=" * 60)
        
        # 判断成功条件：
        # - A类卡片全部成功
        # - B类卡片：只需要 A类数量-1 个成功即可（最后一个B类卡片可能用不上）
        a_success = result['successful_a_cards'] == result['total_a_cards']
        expected_b = result['total_a_cards'] - 1  # 连线数量 = 节点数 - 1
        b_success = result['successful_b_cards'] >= expected_b
        
        return a_success and b_success
        
    except FileNotFoundError as e:
        print(f"\n[错误] {e}")
        return False
    except ValueError as e:
        print(f"\n[错误] {e}")
        return False
    except RuntimeError as e:
        print(f"\n[错误] API调用失败: {e}")
        return False
    except Exception as e:
        print(f"\n[错误] 注入失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def inject_only_mode(md_path: str, preview_only: bool = False, verbose: bool = False):
    """
    仅注入模式 - 直接注入已生成的Markdown文件
    
    Args:
        md_path: Markdown文件路径
        preview_only: 是否仅预览
        verbose: 详细输出
    """
    md_path = os.path.abspath(md_path)
    
    if not os.path.exists(md_path):
        print(f"错误: 文件不存在: {md_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("教学卡片注入工具 (仅注入模式)")
    print("=" * 60)
    
    success = inject_cards_to_platform(md_path, preview_only, verbose)
    
    if success:
        print("\n[完成] 注入成功!")
    else:
        print("\n[失败] 注入过程中出现错误")
        sys.exit(1)


def set_project_from_url(url: str):
    """
    从智慧树页面URL提取课程ID和训练任务ID，并更新.env文件
    
    URL格式示例:
    https://hike-teaching-center.polymas.com/tch-hike/agent-course-full/5vamqyyzvecvnoY4NKa4/ability-training/create?trainTaskId=WwD67NeKNVsyMrpypxkJ
    
    Args:
        url: 智慧树页面URL
    """
    import re
    
    print("=" * 60)
    print("从URL提取项目配置")
    print("=" * 60)
    print(f"\nURL: {url}\n")
    
    # 提取课程ID (agent-course-full/后面的部分)
    course_match = re.search(r'agent-course-full/([^/]+)', url)
    course_id = course_match.group(1) if course_match else None
    
    # 提取训练任务ID (trainTaskId=后面的部分)
    task_match = re.search(r'trainTaskId=([^&]+)', url)
    train_task_id = task_match.group(1) if task_match else None
    
    if not course_id:
        print("[错误] 无法从URL提取课程ID")
        print("请确保URL包含 agent-course-full/<课程ID> 部分")
        sys.exit(1)
    
    if not train_task_id:
        print("[错误] 无法从URL提取训练任务ID")
        print("请确保URL包含 trainTaskId=<任务ID> 参数")
        sys.exit(1)
    
    print(f"提取到的配置:")
    print(f"  课程ID: {course_id}")
    print(f"  训练任务ID: {train_task_id}")
    
    # 更新.env文件
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            env_content = f.read()
        
        # 更新课程ID
        if 'PLATFORM_COURSE_ID=' in env_content:
            env_content = re.sub(
                r'PLATFORM_COURSE_ID=.*',
                f'PLATFORM_COURSE_ID={course_id}',
                env_content
            )
        else:
            env_content += f'\nPLATFORM_COURSE_ID={course_id}'
        
        # 更新训练任务ID
        if 'PLATFORM_TRAIN_TASK_ID=' in env_content:
            env_content = re.sub(
                r'PLATFORM_TRAIN_TASK_ID=.*',
                f'PLATFORM_TRAIN_TASK_ID={train_task_id}',
                env_content
            )
        else:
            env_content += f'\nPLATFORM_TRAIN_TASK_ID={train_task_id}'
        
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(env_content)
        
        print(f"\n[成功] 已更新 .env 文件")
        print("\n" + "=" * 50)
        print("[重要] 还需要手动获取以下配置:")
        print("=" * 50)
        print("打开浏览器开发者工具(F12)，在Console中找到：")
        print("  1. 训练开始节点 (type: 'SCRIPT_START') 的 id")
        print("  2. 训练结束节点 (type: 'SCRIPT_END') 的 id")
        print("\n然后在 .env 中设置:")
        print("  PLATFORM_START_NODE_ID=<训练开始节点ID>")
        print("  PLATFORM_END_NODE_ID=<训练结束节点ID>")
        print("=" * 50)
    else:
        print(f"\n[警告] .env 文件不存在: {env_path}")
        print(f"请手动添加以下配置:")
        print(f"  PLATFORM_COURSE_ID={course_id}")
        print(f"  PLATFORM_TRAIN_TASK_ID={train_task_id}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='教学卡片自动生成脚本 - 从教学剧本生成 A/B 类卡片',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基本用法：生成卡片
  python main.py --input "./input/剧本.docx"
  python main.py --input "./input/剧本.pdf" --output "./output/课程卡片.md"
  python main.py --input "./input/剧本.md" --preview

  # 生成并注入到平台
  python main.py --input "./input/剧本.docx" --inject
  python main.py --input "./input/剧本.docx" --preview-inject  # 仅预览，不实际注入

  # 仅注入已生成的文件
  python main.py --inject-only "./output/cards_output_xxx.md"
  python main.py --inject-only "./output/cards_output_xxx.md" --preview-inject

  # 切换项目：从URL自动提取课程ID和训练任务ID
  python main.py --set-project "https://hike-teaching-center.polymas.com/tch-hike/agent-course-full/课程ID/ability-training/create?trainTaskId=任务ID"
        """
    )
    
    parser.add_argument(
        '--input', '-i',
        required=False,  # 在 --inject-only 模式下不需要
        help='输入文件路径（支持 .md, .docx, .pdf 格式）'
    )
    
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='输出文件路径（默认为 output/cards_output_{timestamp}.md）'
    )
    
    parser.add_argument(
        '--preview', '-p',
        action='store_true',
        help='预览模式：只分析剧本结构，不生成卡片'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='详细输出模式'
    )
    
    parser.add_argument(
        '--inject',
        action='store_true',
        help='生成卡片后自动注入到智慧树平台'
    )
    
    parser.add_argument(
        '--inject-only',
        metavar='MD_FILE',
        help='仅注入已生成的Markdown文件到平台（不重新生成）'
    )
    
    parser.add_argument(
        '--preview-inject',
        action='store_true',
        help='预览注入内容（不实际注入）'
    )
    
    parser.add_argument(
        '--set-project',
        metavar='URL',
        help='从智慧树页面URL提取并设置课程ID和训练任务ID'
    )
    
    args = parser.parse_args()
    
    # 处理设置项目模式
    if args.set_project:
        set_project_from_url(args.set_project)
        return
    
    # 处理仅注入模式
    if args.inject_only:
        inject_only_mode(args.inject_only, args.preview_inject, args.verbose)
        return
    
    # 非inject-only模式需要--input参数
    if not args.input:
        parser.error("需要提供 --input 参数，或使用 --inject-only 模式")
    
    # 检查输入文件
    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        print(f"错误: 输入文件不存在: {input_path}")
        sys.exit(1)
    
    # 确定输出路径
    if args.output:
        output_path = os.path.abspath(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"cards_output_{timestamp}.md"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    print("=" * 60)
    print("教学卡片自动生成脚本")
    print("=" * 60)
    print(f"\n输入文件: {input_path}")
    if not args.preview:
        print(f"输出文件: {output_path}")
    print()
    
    try:
        # 步骤1: 解析文件
        print("[1] 步骤1: 解析输入文件...")
        file_parser = get_parser_for_file(input_path)
        content = file_parser(input_path)
        
        if args.verbose:
            print(f"   - 成功解析，内容长度: {len(content)} 字符")
        print("   [OK] 文件解析完成\n")
        
        # 步骤2: 分析内容结构
        print("[2] 步骤2: 分析剧本结构...")
        splitter = ContentSplitter()
        analysis_result = splitter.analyze(content)
        stages = analysis_result['stages']
        
        print(f"   [OK] 识别出 {len(stages)} 个教学阶段\n")
        
        # 预览模式：显示分析结果后退出
        if args.preview:
            print("=" * 60)
            print("预览模式 - 剧本结构分析结果")
            print("=" * 60)
            
            for stage in stages:
                print(f"\n【阶段 {stage['id']}】{stage['title']}")
                print(f"   角色: {stage['role']}")
                print(f"   任务: {stage['task']}")
                print(f"   关键点: {', '.join(stage['key_points'])}")
                if args.verbose:
                    print(f"   内容摘要: {stage['content_excerpt']}")
            
            print("\n" + "=" * 60)
            print("预览完成。移除 --preview 参数以生成卡片。")
            return
        
        # 步骤3: 生成卡片
        print("[3] 步骤3: 生成教学卡片...")
        generator = CardGenerator()
        
        cards_content = generator.generate_all_cards(
            stages, 
            content,
            progress_callback=progress_callback
        )
        
        print("   [OK] 卡片生成完成\n")
        
        # 步骤4: 保存输出
        print("[4] 步骤4: 保存输出文件...")
        
        # 添加文件头信息
        header = f"""# 教学卡片

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 源文件: {os.path.basename(input_path)}
> 阶段数量: {len(stages)}

---

"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(header + cards_content)
        
        print(f"   [OK] 已保存到: {output_path}\n")
        
        # 完成
        print("=" * 60)
        print("[完成] 生成完成！")
        print(f"   共生成 {len(stages) * 2} 张卡片（{len(stages)} 个阶段 × 2）")
        print(f"   输出文件: {output_path}")
        print("=" * 60)
        
        # 如果指定了注入参数，执行注入
        if args.inject or args.preview_inject:
            inject_cards_to_platform(
                output_path, 
                preview_only=args.preview_inject,
                verbose=args.verbose
            )
        
    except FileNotFoundError as e:
        print(f"\n[错误] 文件错误: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"\n[错误] 数据错误: {e}")
        sys.exit(1)
    except ImportError as e:
        print(f"\n[错误] 依赖缺失: {e}")
        print("请运行: pip install -r requirements.txt")
        sys.exit(1)
    except RuntimeError as e:
        print(f"\n[错误] 运行错误: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n[警告] 用户中断操作")
        sys.exit(130)
    except Exception as e:
        print(f"\n[错误] 未知错误: {e}")
        import traceback
        traceback.print_exc()
        print("\n提示: 如果问题与API返回内容相关，请检查您的ANTHROPIC_API_KEY是否正确")
        sys.exit(1)


if __name__ == "__main__":
    main()
