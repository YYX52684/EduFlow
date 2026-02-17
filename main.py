#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
教学卡片自动生成脚本
支持从 Markdown、DOCX、PDF 格式的教学剧本生成 A/B 类教学卡片

功能：卡片生成、学生模拟测试、评估、仅注入、DSPy 优化、人设生成等；具体逻辑在 cli 子模块。
"""
import argparse
import io
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows 下强制 stdout/stderr 使用 UTF-8，避免中文路径/输出乱码
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def main():
    parser = argparse.ArgumentParser(
        description="教学卡片自动生成与模拟测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # ========== 卡片生成 ==========
  python main.py --input "./input/剧本.docx"
  python main.py --input "./input/剧本.docx" --inject
  python main.py --inject-only "./output/cards_output_xxx.md"

  # ========== 学生模拟测试 ==========
  python main.py --simulate "output/cards.md" --persona "excellent"
  python main.py --simulate "output/cards.md" --persona-batch "excellent,average,struggling"

  # ========== 评估 / 人设 / 项目配置 ==========
  python main.py --evaluate "simulator_output/logs/session_xxx.json"
  python main.py --list-personas
  python main.py --generate-personas "./input/剧本.docx"
  python main.py --set-project "https://hike-teaching-center.polymas.com/..."
        """,
    )
    parser.add_argument("--input", "-i", required=False, help="输入文件路径（支持 .md, .docx, .doc, .pdf）")
    parser.add_argument("--output", "-o", default=None, help="输出文件路径（默认为 output/cards_output_{timestamp}.md）")
    parser.add_argument("--workspace", "-w", metavar="NAME", default=None, help="项目名，与 Web 统一：workspaces/<NAME>/input 与 output")
    parser.add_argument("--preview", "-p", action="store_true", help="预览模式：只分析剧本结构，不生成卡片")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--inject", action="store_true", help="生成卡片后自动注入到智慧树平台")
    parser.add_argument("--inject-only", metavar="MD_FILE", help="仅注入已生成的 Markdown 文件到平台")
    parser.add_argument("--preview-inject", action="store_true", help="预览注入内容（不实际注入）")
    parser.add_argument("--set-project", metavar="URL", help="从智慧树页面 URL 提取并设置课程ID和训练任务ID")
    parser.add_argument("--use-dspy", action="store_true", help="使用 DSPy 结构化生成器")
    parser.add_argument("--framework", metavar="ID", default=None, help="指定生成框架 ID（如 default, dspy）")
    parser.add_argument("--list-frameworks", action="store_true", help="列出框架库中所有可用生成框架后退出")

    parser.add_argument("--simulate", metavar="MD_FILE", help="运行学生模拟测试，指定卡片 Markdown 文件")
    parser.add_argument("--persona", default="excellent", help="学生人设 (excellent/average/struggling 或自定义)")
    parser.add_argument("--manual", action="store_true", help="手动输入模式")
    parser.add_argument("--hybrid", action="store_true", help="混合模式")
    parser.add_argument("--persona-batch", metavar="PERSONAS", help="批量测试多种人设，逗号分隔")
    parser.add_argument("--sim-output", default="simulator_output", help="模拟测试输出目录")
    parser.add_argument("--no-eval", action="store_true", help="模拟测试后不运行评估")
    parser.add_argument("--simulate-platform", action="store_true", help="使用平台侧 LLM 进行学生模拟测试")
    parser.add_argument("--platform-step-id", metavar="STEP_ID", default=None, help="平台训练任务起始节点 stepId")

    parser.add_argument("--evaluate", metavar="LOG_FILE", help="评估已有的对话日志文件（JSON）")
    parser.add_argument("--list-personas", action="store_true", help="列出所有可用人设")
    parser.add_argument("--generate-personas", metavar="INPUT_FILE", help="根据原始教学材料生成推荐的学生角色配置")
    parser.add_argument("--num-personas", type=int, default=3, help="生成的角色数量 (默认: 3)")

    parser.add_argument("--optimize-dspy", action="store_true", help="运行 DSPy 生成器优化")
    parser.add_argument("--trainset", metavar="PATH", help="trainset JSON 路径（用于 --optimize-dspy）")
    parser.add_argument("--devset", metavar="PATH", help="可选 devset JSON 路径（用于 --optimize-dspy）")
    parser.add_argument("--build-trainset", metavar="PATH", help="从剧本文件或目录构建 trainset 并保存为 JSON")
    parser.add_argument("--validate-trainset", metavar="PATH", help="校验 trainset JSON 结构")
    parser.add_argument("--cards-output", metavar="PATH", default=None, help="优化时生成卡片的输出路径")
    parser.add_argument("--export-file", metavar="PATH", default=None, help="外部评估导出文件路径")
    parser.add_argument("--optimizer", choices=["bootstrap", "mipro"], default="bootstrap", help="优化器类型")
    parser.add_argument("--max-rounds", type=int, default=None, help="Bootstrap 最大轮数")

    args = parser.parse_args()

    if args.set_project:
        from cli.platform_cfg import set_project_from_url
        set_project_from_url(args.set_project)
        return
    if args.list_frameworks:
        from cli.frameworks import run_list_frameworks
        run_list_frameworks()
        return
    if args.list_personas:
        from cli.personas import list_personas
        list_personas()
        return
    if args.generate_personas:
        from cli.personas import generate_personas
        output_dir = (args.sim_output + "/custom") if args.sim_output != "simulator_output" else None
        generate_personas(
            input_path=os.path.abspath(args.generate_personas),
            num_personas=args.num_personas,
            output_dir=output_dir,
            verbose=args.verbose,
        )
        return
    if args.build_trainset:
        from cli.optimizer import run_build_trainset
        if not args.input:
            parser.error("--build-trainset 需要指定数据来源，请同时提供 --input（文件或目录）")
        run_build_trainset(args.input, args.build_trainset, verbose=args.verbose)
        return
    if args.validate_trainset:
        from cli.optimizer import run_validate_trainset
        run_validate_trainset(args.validate_trainset)
        return
    if args.optimize_dspy:
        from cli.optimizer import run_optimize_dspy
        run_optimize_dspy(args, parser)
        return
    if args.evaluate:
        from cli.simulate import run_evaluation_only
        run_evaluation_only(args.evaluate, args.sim_output)
        return
    if args.simulate and not args.simulate_platform:
        from cli.simulate import run_simulation, run_batch_simulation
        md_path = os.path.abspath(args.simulate)
        if not os.path.exists(md_path):
            print(f"错误: 卡片文件不存在: {md_path}")
            sys.exit(1)
        if args.persona_batch:
            personas = [p.strip() for p in args.persona_batch.split(",")]
            run_batch_simulation(md_path=md_path, personas=personas, output_dir=args.sim_output, verbose=args.verbose)
            return
        mode = "manual" if args.manual else ("hybrid" if args.hybrid else "auto")
        run_simulation(
            md_path=md_path,
            persona_id=args.persona,
            mode=mode,
            output_dir=args.sim_output,
            verbose=args.verbose,
            run_evaluation=not args.no_eval,
        )
        return
    if args.simulate_platform:
        from cli.simulate import run_simulate_platform
        run_simulate_platform(args, parser)
        return
    if args.inject_only:
        from cli.inject import run_inject_only
        run_inject_only(args.inject_only, args.preview_inject, args.verbose)
        return
    if not args.input:
        parser.error("需要提供 --input 参数，或使用 --simulate/--inject-only/--evaluate 等模式")
    from cli.script import run_script
    run_script(args)


if __name__ == "__main__":
    main()
