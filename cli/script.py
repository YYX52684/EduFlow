# -*- coding: utf-8 -*-
"""CLI 默认流程：解析输入 → 分析结构 → 写 trainset → 预览或生成卡片 → 可选注入。"""
import os
import sys
from datetime import datetime

from config import (
    INPUT_DIR,
    OUTPUT_DIR,
    CARD_GENERATOR_TYPE,
    DEEPSEEK_API_KEY,
    EVALUATION_CONFIG,
)
from api.workspace import get_project_dirs
from parsers import (
    parse_docx_with_structure,
    parse_doc_with_structure,
    extract_task_meta_from_doc,
    extract_task_meta_from_content_structure,
)
from generators import ContentSplitter, list_frameworks, get_framework
from generators.evaluation_section import build_evaluation_markdown

from cli.common import get_parser_for_file, progress_callback
from cli.inject import inject_cards_to_platform


def run_script(args):
    """
    执行「需要 --input」的默认流程：解析 → 分析 → 写 trainset → 预览或生成卡片 → 可选注入。
    调用前调用方应已校验 args.input 存在。
    """
    if args.workspace:
        _input_dir, _output_dir, _ = get_project_dirs(args.workspace.strip())
    else:
        _input_dir, _output_dir = INPUT_DIR, OUTPUT_DIR

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

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"cards_output_{timestamp}.md"
    if args.output:
        output_path = os.path.abspath(args.output)
    else:
        output_path = os.path.join(_output_dir, output_filename)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    def _safe_print(s):
        print(s)

    print("=" * 60)
    print("教学卡片自动生成脚本")
    print("=" * 60)
    _safe_print(f"\n输入文件: {input_path}")
    if not args.preview:
        _safe_print(f"输出文件: {output_path}")
    print()

    try:
        # 步骤1: 解析
        print("[1] 步骤1: 解析输入文件...")
        doc_structure = None
        ext_lower = input_path.lower()
        if ext_lower.endswith(".docx"):
            content, raw_structure = parse_docx_with_structure(input_path)
            doc_structure = [{"title": s["title"], "level": s.get("level", 1), "content": s.get("content", "")} for s in raw_structure]
        elif ext_lower.endswith(".doc"):
            content, raw_structure = parse_doc_with_structure(input_path)
            doc_structure = [{"title": s["title"], "level": s.get("level", 1), "content": s.get("content", "")} for s in raw_structure]
        else:
            file_parser = get_parser_for_file(input_path)
            content = file_parser(input_path)
        if args.verbose:
            print(f"   - 成功解析，内容长度: {len(content)} 字符")
        print("   [OK] 文件解析完成\n")

        # 步骤2: 分析
        print("[2] 步骤2: 分析剧本结构...")
        splitter = ContentSplitter()
        analysis_result = splitter.analyze(content)
        stages = analysis_result["stages"]
        print(f"   [OK] 识别出 {len(stages)} 个教学阶段\n")

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
        frameworks = list_frameworks()
        if not frameworks:
            print("   [错误] 框架库中暂无可用生成框架。请在 generators/frameworks/ 下添加框架。")
            sys.exit(1)
        framework_id = args.framework
        if framework_id is None and CARD_GENERATOR_TYPE:
            for m in frameworks:
                if m["id"] == CARD_GENERATOR_TYPE:
                    framework_id = CARD_GENERATOR_TYPE
                    break
        if framework_id is None and args.use_dspy:
            framework_id = "dspy" if any(m["id"] == "dspy" for m in frameworks) else None
        if framework_id is None and len(frameworks) == 1:
            framework_id = frameworks[0]["id"]
        elif framework_id is None and len(frameworks) > 1:
            print("\n   请选择生成框架:")
            for i, m in enumerate(frameworks, 1):
                print(f"     {i}. {m['id']} - {m['name']}")
            try:
                choice = input("   请输入序号或框架 ID [1]: ").strip() or "1"
                if choice.isdigit():
                    idx = int(choice)
                    framework_id = frameworks[idx - 1]["id"] if 1 <= idx <= len(frameworks) else frameworks[0]["id"]
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
        cards_content = generator.generate_all_cards(stages, content, progress_callback=progress_callback)
        print("   [OK] 卡片生成完成\n")

        # 步骤4: 保存
        print("[4] 步骤4: 保存输出文件...")
        try:
            if doc_structure is not None:
                task_meta = extract_task_meta_from_content_structure(
                    content, doc_structure, os.path.splitext(os.path.basename(input_path))[0]
                )
            else:
                task_meta = extract_task_meta_from_doc(input_path)
        except (ValueError, FileNotFoundError):
            task_meta = {"task_name": os.path.basename(input_path), "description": "", "evaluation_items": []}

        if EVALUATION_CONFIG.get("enabled", True):
            evaluation_md = build_evaluation_markdown(
                task_meta.get("evaluation_items", []),
                stages,
                target_total_score=EVALUATION_CONFIG.get("target_total_score", 100),
                auto_generate_if_empty=EVALUATION_CONFIG.get("auto_generate", True),
            )
            if evaluation_md:
                cards_content = cards_content + "\n\n---\n\n" + evaluation_md

        header = f"""# 教学卡片

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 源文件: {os.path.basename(input_path)}
> 阶段数量: {len(stages)}

---

"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header + cards_content)
        _safe_print(f"   [OK] 已保存到: {output_path}\n")

        print("=" * 60)
        print("[完成] 生成完成！")
        print(f"   共生成 {len(stages) * 2} 张卡片（{len(stages)} 个阶段 × 2）")
        _safe_print(f"   输出文件: {output_path}")
        print("=" * 60)

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
