#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
教学卡片自动生成脚本
支持从 Markdown、DOCX、PDF 格式的教学剧本生成 A/B 类教学卡片

新增功能：
- 学生模拟测试：使用LLM模拟学生与卡片NPC进行对话
- 交互质量评估：基于对话日志生成多维度评估报告
"""
import argparse
import os
import sys
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    INPUT_DIR,
    OUTPUT_DIR,
    PLATFORM_CONFIG,
    PLATFORM_ENDPOINTS,
    CARD_GENERATOR_TYPE,
    DEEPSEEK_API_KEY,
    DOUBAO_API_KEY,
    DEFAULT_MODEL_TYPE,
    EVALUATION_CONFIG,
    DSPY_OPTIMIZER_CONFIG,
)
from api.workspace import get_workspace_dirs
from parsers import (
    parse_markdown,
    parse_docx,
    parse_docx_with_structure,
    parse_pdf,
    extract_task_meta_from_doc,
    extract_task_meta_from_content_structure,
)
from generators import ContentSplitter, CardGenerator, DSPyCardGenerator, DSPY_AVAILABLE, list_frameworks, get_framework
from generators.evaluation_section import build_evaluation_markdown
from api_platform import PlatformAPIClient, CardInjector


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


def inject_cards_to_platform(
    md_path: str,
    task_name: str = None,
    description: str = None,
    preview_only: bool = False,
    verbose: bool = False,
) -> bool:
    """
    将Markdown文件中的卡片注入到平台，并可选配置任务名称/描述与评价项。
    
    Args:
        md_path: Markdown文件路径
        task_name: 任务名称（为空则不调用 editConfiguration）
        description: 任务描述（为空则不调用 editConfiguration）
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
        
        # 执行注入（含任务配置与评价项）
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
        
        # 显示结果
        print("\n" + "-" * 40)
        print("注入结果:")
        print(f"  A类卡片（节点）: {result['successful_a_cards']}/{result['total_a_cards']} 成功")
        print(f"  B类卡片（连线）: {result['successful_b_cards']}/{result['total_b_cards']} 成功")
        if result.get("evaluation_items_count") is not None:
            print(f"  评价项: {result['evaluation_items_count']} 个，总分 {result.get('total_score', 0)}")
        
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


def run_simulation(
    md_path: str,
    persona_id: str = "excellent",
    mode: str = "auto",
    output_dir: str = "simulator_output",
    verbose: bool = False,
    run_evaluation: bool = True,
):
    """
    运行学生模拟测试
    
    Args:
        md_path: 卡片Markdown文件路径
        persona_id: 人设标识符 (excellent/average/struggling 或自定义文件路径)
        mode: 会话模式 (auto/manual/hybrid)
        output_dir: 输出目录
        verbose: 详细输出
        run_evaluation: 是否运行评估
    """
    from simulator import SessionRunner, SessionConfig, SessionMode
    from simulator import Evaluator, EvaluatorFactory
    
    print("=" * 60)
    print("学生模拟测试")
    print("=" * 60)
    print(f"\n卡片文件: {md_path}")
    print(f"人设: {persona_id}")
    print(f"模式: {mode}")
    print()
    
    # 创建会话配置
    config = SessionConfig(
        mode=SessionMode(mode),
        persona_id=persona_id,
        output_dir=output_dir,
        verbose=verbose,
    )
    
    # 创建并运行会话
    runner = SessionRunner(config)
    runner.load_cards(md_path)
    runner.setup()
    
    try:
        log = runner.run()
        
        # 运行评估
        if run_evaluation and log.summary.get("status") == "completed":
            print("\n" + "=" * 60)
            print("开始评估对话质量...")
            print("=" * 60)
            
            evaluator = EvaluatorFactory.create_from_env()
            dialogue = runner.get_dialogue_for_evaluation()
            
            report = evaluator.evaluate(
                dialogue,
                session_id=log.session_id
            )
            
            # 保存报告
            reports_dir = os.path.join(output_dir, "reports")
            evaluator.save_report(report, reports_dir)
            
            print("\n[完成] 模拟测试和评估已完成!")
        else:
            print("\n[完成] 模拟测试已完成（跳过评估）")
            
    except KeyboardInterrupt:
        print("\n[中断] 用户中断测试")
    except Exception as e:
        print(f"\n[错误] 模拟测试失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def run_batch_simulation(
    md_path: str,
    personas: list,
    output_dir: str = "simulator_output",
    verbose: bool = False,
):
    """
    批量运行多个人设的模拟测试
    
    Args:
        md_path: 卡片Markdown文件路径
        personas: 人设列表
        output_dir: 输出目录
        verbose: 详细输出
    """
    print("=" * 60)
    print("批量学生模拟测试")
    print("=" * 60)
    print(f"\n卡片文件: {md_path}")
    print(f"人设列表: {', '.join(personas)}")
    print()
    
    results = []
    
    for i, persona in enumerate(personas, 1):
        print(f"\n{'='*40}")
        print(f"[{i}/{len(personas)}] 测试人设: {persona}")
        print(f"{'='*40}")
        
        # 为每个人设创建单独的输出目录
        persona_output = os.path.join(output_dir, f"persona_{persona}")
        
        try:
            run_simulation(
                md_path=md_path,
                persona_id=persona,
                mode="auto",
                output_dir=persona_output,
                verbose=verbose,
                run_evaluation=True,
            )
            results.append((persona, "成功"))
        except Exception as e:
            print(f"[错误] 人设 {persona} 测试失败: {e}")
            results.append((persona, f"失败: {e}"))
    
    # 显示批量测试结果
    print("\n" + "=" * 60)
    print("批量测试结果汇总")
    print("=" * 60)
    for persona, status in results:
        print(f"  - {persona}: {status}")


def run_evaluation_only(log_path: str, output_dir: str = None):
    """
    仅运行评估（对已有的对话日志）
    
    Args:
        log_path: 会话日志文件路径（JSON格式）
        output_dir: 输出目录
    """
    from simulator import evaluate_session
    
    print("=" * 60)
    print("对话质量评估")
    print("=" * 60)
    print(f"\n日志文件: {log_path}")
    
    if not os.path.exists(log_path):
        print(f"[错误] 日志文件不存在: {log_path}")
        sys.exit(1)
    
    try:
        report = evaluate_session(log_path, output_dir)
        print(f"\n[完成] 评估完成!")
        print(f"  总分: {report.total_score:.1f}/100")
        print(f"  评级: {report.get_rating()}")
    except Exception as e:
        print(f"\n[错误] 评估失败: {e}")
        sys.exit(1)


def generate_personas(
    input_path: str,
    num_personas: int = 3,
    output_dir: str = None,
    verbose: bool = False,
):
    """
    根据原始教学材料生成推荐的学生角色配置
    
    Args:
        input_path: 输入文件路径（剧本、课程大纲等）
        num_personas: 生成的角色数量
        output_dir: 输出目录
        verbose: 详细输出
    """
    from simulator import PersonaGeneratorFactory
    
    print("=" * 60)
    print("智能角色生成器")
    print("=" * 60)
    print(f"\n输入文件: {input_path}")
    print(f"生成数量: {num_personas}")
    print()
    
    # 读取输入文件
    if not os.path.exists(input_path):
        print(f"[错误] 文件不存在: {input_path}")
        sys.exit(1)
    
    # 根据文件类型解析内容
    try:
        file_parser = get_parser_for_file(input_path)
        content = file_parser(input_path)
        print(f"[OK] 已读取文件，内容长度: {len(content)} 字符")
    except ValueError as e:
        # 如果不是支持的格式，尝试直接读取文本
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"[OK] 已读取文本文件，内容长度: {len(content)} 字符")
    
    # 创建生成器
    print("\n[生成] 正在调用Sonnet生成角色配置...")
    generator = PersonaGeneratorFactory.create_from_env()
    
    try:
        personas = generator.generate_from_material(
            material_content=content,
            num_personas=num_personas,
            include_preset_types=True,
        )
        
        print(f"\n[OK] 成功生成 {len(personas)} 个角色配置")
        
        # 显示生成结果
        print("\n" + "-" * 40)
        print("生成的角色概览:")
        print("-" * 40)
        for i, persona in enumerate(personas, 1):
            print(f"\n【角色 {i}】{persona.name}")
            print(f"  背景: {persona.background[:50]}..." if len(persona.background) > 50 else f"  背景: {persona.background}")
            print(f"  性格: {persona.personality}")
            print(f"  目标: {persona.goal[:50]}..." if len(persona.goal) > 50 else f"  目标: {persona.goal}")
            print(f"  参与度: {persona.engagement_level}")
            if verbose:
                print(f"  优势: {', '.join(persona.strengths[:3])}")
                print(f"  不足: {', '.join(persona.weaknesses[:2])}")
        
        # 保存到文件
        saved_paths = generator.save_personas(personas, output_dir)
        
        print("\n" + "-" * 40)
        print("已保存角色配置文件:")
        print("-" * 40)
        for path in saved_paths:
            print(f"  - {path}")
        
        print("\n" + "=" * 60)
        print("[完成] 角色生成成功!")
        print("\n使用方法:")
        for i, path in enumerate(saved_paths):
            filename = os.path.basename(path)
            print(f"  python main.py --simulate <cards.md> --persona \"custom/{filename}\"")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[错误] 角色生成失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def list_personas():
    """列出可用的人设"""
    from simulator import PersonaManager
    
    print("=" * 60)
    print("可用人设列表")
    print("=" * 60)
    
    manager = PersonaManager()
    
    print("\n【预设人设】")
    for name in manager.list_presets():
        print(f"  - {name}")
    
    print("\n【自定义人设】")
    custom = manager.list_custom()
    if custom:
        for name in custom:
            print(f"  - custom/{name}")
    else:
        print("  (暂无)")
    
    print("\n使用方法:")
    print("  --persona excellent        # 使用预设人设")
    print("  --persona custom/xxx.yaml  # 使用自定义人设")
    print("  --generate-personas <input_file>  # 根据材料生成推荐人设")


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
        description='教学卡片自动生成与模拟测试工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # ========== 卡片生成 ==========
  # 基本用法：生成卡片
  python main.py --input "./input/剧本.docx"
  python main.py --input "./input/剧本.pdf" --output "./output/课程卡片.md"
  python main.py --input "./input/剧本.md" --preview

  # 生成并注入到平台
  python main.py --input "./input/剧本.docx" --inject
  python main.py --input "./input/剧本.docx" --preview-inject

  # 仅注入已生成的文件
  python main.py --inject-only "./output/cards_output_xxx.md"

  # ========== 学生模拟测试 ==========
  # 自动模式（LLM扮演学生）
  python main.py --simulate "output/cards_output_xxx.md" --persona "excellent"
  
  # 手动模式（终端输入）
  python main.py --simulate "output/cards_output_xxx.md" --manual
  
  # 混合模式
  python main.py --simulate "output/cards_output_xxx.md" --persona "average" --hybrid
  
  # 使用自定义人设
  python main.py --simulate "output/cards.md" --persona "custom/entrepreneur.yaml"
  
  # 批量测试多种人设
  python main.py --simulate "output/cards.md" --persona-batch "excellent,average,struggling"
  
  # 指定输出目录
  python main.py --simulate "output/cards.md" --persona "excellent" --sim-output "simulator_output/"

  # ========== 评估 ==========
  # 评估已有的对话日志
  python main.py --evaluate "simulator_output/logs/session_xxx.json"
  
  # 列出可用人设
  python main.py --list-personas

  # ========== 智能角色生成 ==========
  # 根据原始剧本生成推荐的学生角色
  python main.py --generate-personas "./input/剧本.docx"
  
  # 指定生成数量
  python main.py --generate-personas "./input/剧本.md" --num-personas 5

  # ========== 项目配置 ==========
  python main.py --set-project "https://hike-teaching-center.polymas.com/..."
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
        '--workspace', '-w',
        metavar='NAME',
        default=None,
        help='项目名，与 Web 统一：使用 workspaces/<NAME>/input 与 output；不指定则用根目录 input/output'
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
    
    parser.add_argument(
        '--use-dspy',
        action='store_true',
        help='使用DSPy结构化生成器（推荐，可减少括号等违规输出）'
    )
    
    parser.add_argument(
        '--framework',
        metavar='ID',
        default=None,
        help='指定生成框架 ID（如 default, dspy）。不指定时根据配置或交互选择'
    )
    
    parser.add_argument(
        '--list-frameworks',
        action='store_true',
        help='列出框架库中所有可用生成框架后退出'
    )
    
    # ========== 学生模拟测试参数 ==========
    parser.add_argument(
        '--simulate',
        metavar='MD_FILE',
        help='运行学生模拟测试，指定卡片Markdown文件'
    )
    
    parser.add_argument(
        '--persona',
        default='excellent',
        help='学生人设 (excellent/average/struggling 或自定义文件路径)'
    )
    
    parser.add_argument(
        '--manual',
        action='store_true',
        help='手动输入模式（从终端输入学生回复）'
    )
    
    parser.add_argument(
        '--hybrid',
        action='store_true',
        help='混合模式（可在自动和手动间切换）'
    )
    
    parser.add_argument(
        '--persona-batch',
        metavar='PERSONAS',
        help='批量测试多种人设，逗号分隔 (如: excellent,average,struggling)'
    )
    
    parser.add_argument(
        '--sim-output',
        default='simulator_output',
        help='模拟测试输出目录 (默认: simulator_output)'
    )
    
    parser.add_argument(
        '--no-eval',
        action='store_true',
        help='模拟测试后不运行评估'
    )
    
    # ========== 评估参数 ==========
    parser.add_argument(
        '--evaluate',
        metavar='LOG_FILE',
        help='评估已有的对话日志文件（JSON格式）'
    )
    
    parser.add_argument(
        '--list-personas',
        action='store_true',
        help='列出所有可用的人设'
    )
    
    # ========== 角色生成参数 ==========
    parser.add_argument(
        '--generate-personas',
        metavar='INPUT_FILE',
        help='根据原始教学材料生成推荐的学生角色配置'
    )
    
    parser.add_argument(
        '--num-personas',
        type=int,
        default=3,
        help='生成的角色数量 (默认: 3)'
    )
    
    # ========== DSPy 优化参数 ==========
    parser.add_argument(
        '--optimize-dspy',
        action='store_true',
        help='运行 DSPy 生成器优化（使用外部评估导出文件作为指标）'
    )
    parser.add_argument(
        '--trainset',
        metavar='PATH',
        help='trainset JSON 路径（用于 --optimize-dspy）；或构建时作为输出路径'
    )
    parser.add_argument(
        '--devset',
        metavar='PATH',
        help='可选 devset JSON 路径（用于 --optimize-dspy）'
    )
    parser.add_argument(
        '--build-trainset',
        metavar='PATH',
        help='从剧本文件或目录构建 trainset 并保存为 JSON（路径为输出文件）'
    )
    parser.add_argument(
        '--validate-trainset',
        metavar='PATH',
        help='校验 trainset JSON 结构与评估标准对齐（见 Operations.md）'
    )
    parser.add_argument(
        '--cards-output',
        metavar='PATH',
        default=None,
        help='优化时生成卡片的输出路径（默认: output/optimizer/cards_for_eval.md）'
    )
    parser.add_argument(
        '--export-file',
        metavar='PATH',
        default=None,
        help='外部评估导出文件路径（优化时读取分数，默认: output/optimizer/export_score.json）'
    )
    parser.add_argument(
        '--optimizer',
        choices=['bootstrap', 'mipro'],
        default='bootstrap',
        help='优化器类型 (默认: bootstrap)'
    )
    parser.add_argument(
        '--max-rounds',
        type=int,
        default=None,
        help='Bootstrap 最大轮数（默认使用配置）'
    )
    
    args = parser.parse_args()
    
    # 处理设置项目模式
    if args.set_project:
        set_project_from_url(args.set_project)
        return
    
    # 处理列出生成框架
    if args.list_frameworks:
        frameworks = list_frameworks()
        if not frameworks:
            print("框架库中暂无可用生成框架。请在 generators/frameworks/ 下添加框架。")
            return
        print("可用生成框架:")
        print("-" * 50)
        for i, m in enumerate(frameworks, 1):
            print(f"  {i}. {m['id']} - {m['name']}")
            if m.get('description'):
                print(f"     {m['description']}")
        print("-" * 50)
        return
    
    # 处理列出人设
    if args.list_personas:
        list_personas()
        return
    
    # 处理角色生成
    if args.generate_personas:
        generate_personas(
            input_path=os.path.abspath(args.generate_personas),
            num_personas=args.num_personas,
            output_dir=args.sim_output + "/custom" if args.sim_output != "simulator_output" else None,
            verbose=args.verbose,
        )
        return
    
    # 处理构建 trainset
    if args.build_trainset:
        from generators.trainset_builder import build_trainset_from_path, save_trainset
        if not args.input:
            parser.error("--build-trainset 需要指定数据来源，请同时提供 --input（文件或目录）")
        print("=" * 60)
        print("构建 DSPy trainset")
        print("=" * 60)
        print(f"  数据来源: {args.input}")
        print(f"  输出文件: {args.build_trainset}\n")
        examples = build_trainset_from_path(args.input, verbose=args.verbose)
        save_trainset(examples, args.build_trainset)
        print(f"  [OK] 已保存 {len(examples)} 条样本到 {args.build_trainset}\n")
        return

    # 处理 trainset 校验
    if args.validate_trainset:
        from generators.trainset_builder import check_trainset_file
        path = os.path.abspath(args.validate_trainset)
        print("校验 trainset 结构与评估标准对齐")
        print(f"  文件: {path}\n")
        valid, messages = check_trainset_file(path, strict=False, check_eval_alignment=True)
        for m in messages:
            print(f"  {m}")
        if valid:
            print("\n  [OK] 通过（仅有建议时可忽略）")
        else:
            print("\n  [失败] 存在结构错误，请修正后再用于 --optimize-dspy 或生成卡片")
        return

    # 处理 DSPy 优化
    if args.optimize_dspy:
        if not DSPY_AVAILABLE:
            print("错误: 未安装 dspy-ai，请运行 pip install dspy-ai")
            sys.exit(1)
        if not args.trainset:
            parser.error("--optimize-dspy 需要提供 --trainset（trainset JSON 路径）")
        from generators.dspy_optimizer import run_optimize_dspy
        cfg = DSPY_OPTIMIZER_CONFIG
        _opt_out = get_workspace_dirs(args.workspace.strip())[1] if args.workspace else OUTPUT_DIR
        output_cards = args.cards_output or cfg.get("cards_output_path", os.path.join(_opt_out, "optimizer", "cards_for_eval.md"))
        export_path = args.export_file or cfg.get("export_file_path", os.path.join(_opt_out, "optimizer", "export_score.json"))
        # 根据导出文件扩展名自动选择解析器：.md -> md，否则用配置
        _ext = os.path.splitext(export_path)[1].lower()
        _parser = "md" if _ext in (".md", ".markdown") else cfg.get("parser", "json")
        export_config = {
            "parser": _parser,
            "json_score_key": cfg.get("json_score_key", "total_score"),
            "csv_score_column": cfg.get("csv_score_column"),
        }
        print("=" * 60)
        print("DSPy 生成器优化")
        print("=" * 60)
        print(f"  trainset: {args.trainset}")
        print(f"  卡片输出: {output_cards}")
        print(f"  导出文件（读取分数）: {export_path}\n")
        model_type = DEFAULT_MODEL_TYPE
        api_key = DOUBAO_API_KEY if model_type == "doubao" else DEEPSEEK_API_KEY
        try:
            compiled = run_optimize_dspy(
                trainset_path=os.path.abspath(args.trainset),
                devset_path=os.path.abspath(args.devset) if args.devset else None,
                output_cards_path=os.path.abspath(output_cards),
                export_path=os.path.abspath(export_path),
                export_config=export_config,
                optimizer_type=args.optimizer,
                api_key=api_key,
                model_type=model_type,
                max_rounds=args.max_rounds or cfg.get("max_rounds", 1),
                max_bootstrapped_demos=cfg.get("max_bootstrapped_demos", 4),
            )
            print("\n  [OK] 优化完成。优化后的程序已返回（后续可接入保存/加载）。")
        except Exception as e:
            print(f"\n[错误] 优化失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        return
    
    # 处理评估模式
    if args.evaluate:
        run_evaluation_only(args.evaluate, args.sim_output)
        return
    
    # 处理学生模拟测试模式
    if args.simulate:
        md_path = os.path.abspath(args.simulate)
        
        if not os.path.exists(md_path):
            print(f"错误: 卡片文件不存在: {md_path}")
            sys.exit(1)
        
        # 批量测试模式
        if args.persona_batch:
            personas = [p.strip() for p in args.persona_batch.split(',')]
            run_batch_simulation(
                md_path=md_path,
                personas=personas,
                output_dir=args.sim_output,
                verbose=args.verbose,
            )
            return
        
        # 确定会话模式
        if args.manual:
            mode = "manual"
        elif args.hybrid:
            mode = "hybrid"
        else:
            mode = "auto"
        
        run_simulation(
            md_path=md_path,
            persona_id=args.persona,
            mode=mode,
            output_dir=args.sim_output,
            verbose=args.verbose,
            run_evaluation=not args.no_eval,
        )
        return
    
    # 处理仅注入模式
    if args.inject_only:
        inject_only_mode(args.inject_only, args.preview_inject, args.verbose)
        return
    
    # 非其他模式需要--input参数
    if not args.input:
        parser.error("需要提供 --input 参数，或使用 --simulate/--inject-only/--evaluate 等模式")
    
    # 统一目录：--workspace 时用 workspaces/<项目名>/，否则用根目录 input/output
    if args.workspace:
        _input_dir, _output_dir, _ = get_workspace_dirs(args.workspace.strip())
    else:
        _input_dir, _output_dir = INPUT_DIR, OUTPUT_DIR
    
    # 检查输入文件并解析路径
    if os.path.isabs(args.input) and os.path.exists(args.input):
        input_path = args.input
    elif args.workspace:
        rel = args.input.replace("input/", "").lstrip("/").replace("\\", "/") or os.path.basename(args.input)
        input_path = os.path.normpath(os.path.join(_input_dir, rel))
    else:
        input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        try:
            print(f"错误: 输入文件不存在: {input_path}")
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                print("错误: 输入文件不存在:", os.path.basename(input_path))
            except Exception:
                print("错误: 输入文件不存在，请检查 --input 与 --workspace")
        sys.exit(1)
    
    # 确定输出路径
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"cards_output_{timestamp}.md"
    if args.output:
        output_path = os.path.abspath(args.output)
    else:
        output_path = os.path.join(_output_dir, output_filename)
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    def _safe_print(s):
        try:
            print(s)
        except UnicodeEncodeError:
            print(s.encode(sys.getdefaultencoding(), errors="replace").decode())
    print("=" * 60)
    print("教学卡片自动生成脚本")
    print("=" * 60)
    _safe_print(f"\n输入文件: {input_path}")
    if not args.preview:
        _safe_print(f"输出文件: {output_path}")
    print()
    
    try:
        # 步骤1: 解析文件（docx 一次打开同时得到正文与结构，避免后续再打开）
        print("[1] 步骤1: 解析输入文件...")
        doc_structure = None
        if input_path.lower().endswith(".docx"):
            content, raw_structure = parse_docx_with_structure(input_path)
            doc_structure = [{"title": s["title"], "level": s.get("level", 1), "content": s.get("content", "")} for s in raw_structure]
        else:
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

        # 解析时同步写入 trainset.json（供 DSPy 优化器使用）
        try:
            from generators.trainset_builder import append_trainset_example
            trainset_path = os.path.join(_output_dir, "optimizer", "trainset.json")
            os.makedirs(os.path.dirname(trainset_path), exist_ok=True)
            count = append_trainset_example(content, stages, trainset_path, source_file=input_path)
            if args.verbose:
                print(f"   [trainset] 已写入 {trainset_path}，当前共 {count} 条\n")
        except Exception as e:
            if args.verbose:
                print(f"   [trainset] 写入跳过: {e}\n")
        
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
        
        # 选择生成框架
        frameworks = list_frameworks()
        if not frameworks:
            print("   [错误] 框架库中暂无可用生成框架。请在 generators/frameworks/ 下添加框架。")
            sys.exit(1)
        
        framework_id = args.framework
        if framework_id is None and CARD_GENERATOR_TYPE:
            # 配置中的 CARD_GENERATOR_TYPE 与某框架 id 一致则直接使用
            for m in frameworks:
                if m["id"] == CARD_GENERATOR_TYPE:
                    framework_id = CARD_GENERATOR_TYPE
                    break
        if framework_id is None and args.use_dspy:
            framework_id = "dspy" if any(m["id"] == "dspy" for m in frameworks) else None
        
        if framework_id is None and len(frameworks) == 1:
            framework_id = frameworks[0]["id"]
        elif framework_id is None and len(frameworks) > 1:
            # 交互式选择
            print("\n   请选择生成框架:")
            for i, m in enumerate(frameworks, 1):
                print(f"     {i}. {m['id']} - {m['name']}")
            try:
                choice = input("   请输入序号或框架 ID [1]: ").strip() or "1"
                if choice.isdigit():
                    idx = int(choice)
                    if 1 <= idx <= len(frameworks):
                        framework_id = frameworks[idx - 1]["id"]
                    else:
                        framework_id = frameworks[0]["id"]
                else:
                    framework_id = choice
            except (EOFError, KeyboardInterrupt):
                framework_id = frameworks[0]["id"]
                print(f"   使用默认: {frameworks[0]['name']}")
        
        if framework_id is None:
            framework_id = frameworks[0]["id"]
        
        try:
            GeneratorClass, meta = get_framework(framework_id)
            print(f"   [INFO] 使用生成框架: {meta['name']}")
        except ValueError as e:
            print(f"   [错误] {e}")
            sys.exit(1)
        
        try:
            generator = GeneratorClass(api_key=DEEPSEEK_API_KEY)
        except Exception as e:
            print(f"   [错误] 初始化生成框架失败: {e}")
            sys.exit(1)
        
        cards_content = generator.generate_all_cards(
            stages,
            content,
            progress_callback=progress_callback
        )
        
        print("   [OK] 卡片生成完成\n")
        
        # 步骤4: 保存输出（含评价项章节）
        print("[4] 步骤4: 保存输出文件...")
        
        # 从输入文档提取任务元数据（复用步骤1已解析的 content/structure，避免 docx 二次打开）
        try:
            if doc_structure is not None:
                task_meta = extract_task_meta_from_content_structure(
                    content, doc_structure, os.path.splitext(os.path.basename(input_path))[0]
                )
            else:
                task_meta = extract_task_meta_from_doc(input_path)
        except (ValueError, FileNotFoundError):
            task_meta = {
                "task_name": os.path.basename(input_path),
                "description": "",
                "evaluation_items": [],
            }
        
        # 追加评价项章节（原文档有则用，否则按阶段自动生成）
        if EVALUATION_CONFIG.get("enabled", True):
            evaluation_md = build_evaluation_markdown(
                task_meta.get("evaluation_items", []),
                stages,
                target_total_score=EVALUATION_CONFIG.get("target_total_score", 100),
                auto_generate_if_empty=EVALUATION_CONFIG.get("auto_generate", True),
            )
            if evaluation_md:
                cards_content = cards_content + "\n\n---\n\n" + evaluation_md
        
        # 添加文件头信息
        header = f"""# 教学卡片

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 源文件: {os.path.basename(input_path)}
> 阶段数量: {len(stages)}

---

"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(header + cards_content)
        
        _safe_print(f"   [OK] 已保存到: {output_path}\n")
        
        # 完成
        print("=" * 60)
        print("[完成] 生成完成！")
        print(f"   共生成 {len(stages) * 2} 张卡片（{len(stages)} 个阶段 × 2）")
        _safe_print(f"   输出文件: {output_path}")
        print("=" * 60)
        
        # 如果指定了注入参数，执行注入（传入从输入文档提取的任务名与描述）
        if args.inject or args.preview_inject:
            inject_cards_to_platform(
                output_path,
                task_name=task_meta.get("task_name"),
                description=task_meta.get("description"),
                preview_only=args.preview_inject,
                verbose=args.verbose,
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
        print("\n提示: 如果问题与API返回内容相关，请检查您的 DEEPSEEK_API_KEY 是否正确")
        sys.exit(1)


if __name__ == "__main__":
    main()
