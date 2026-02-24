# -*- coding: utf-8 -*-
"""CLI DSPy 优化：构建/校验 trainset、运行 DSPy 优化。"""
import os
import sys

from config import (
    OUTPUT_DIR,
    DSPY_OPTIMIZER_CONFIG,
    DEFAULT_MODEL_TYPE,
    DEEPSEEK_API_KEY,
    DOUBAO_API_KEY,
)
from api.workspace import get_project_dirs


def run_build_trainset(input_path: str, output_path: str, verbose: bool = False):
    """从文件或目录构建 trainset 并保存为 JSON。"""
    from generators.trainset_builder import build_trainset_from_path, save_trainset

    print("=" * 60)
    print("构建 DSPy trainset")
    print("=" * 60)
    print(f"  数据来源: {input_path}")
    print(f"  输出文件: {output_path}\n")
    examples = build_trainset_from_path(input_path, verbose=verbose)
    save_trainset(examples, output_path)
    print(f"  [OK] 已保存 {len(examples)} 条样本到 {output_path}\n")


def run_validate_trainset(path: str):
    """校验 trainset JSON 结构与评估标准对齐。"""
    from generators.trainset_builder import check_trainset_file

    path = os.path.abspath(path)
    print("校验 trainset 结构与评估标准对齐")
    print(f"  文件: {path}\n")
    valid, messages = check_trainset_file(path, strict=False, check_eval_alignment=True)
    for m in messages:
        print(f"  {m}")
    if valid:
        print("\n  [OK] 通过（仅有建议时可忽略）")
    else:
        print("\n  [失败] 存在结构错误，请修正后再用于 --optimize-dspy 或生成卡片")


def run_optimize_dspy(
    args,
    parser,
):
    """运行 DSPy 生成器优化。需要 args.trainset；可选 args.devset, args.workspace, args.cards_output, args.export_file, args.optimizer, args.max_rounds。"""
    from generators import DSPY_AVAILABLE
    if not DSPY_AVAILABLE:
        print("错误: 未安装 dspy-ai，请运行 pip install dspy-ai")
        sys.exit(1)
    from generators.dspy_optimizer import run_optimize_dspy, build_export_config

    if not args.trainset:
        parser.error("--optimize-dspy 需要提供 --trainset（trainset JSON 路径）")
    cfg = DSPY_OPTIMIZER_CONFIG
    _opt_out = get_project_dirs(args.workspace.strip())[1] if args.workspace else OUTPUT_DIR
    output_cards = args.cards_output or cfg.get("cards_output_path", os.path.join(_opt_out, "optimizer", "cards_for_eval.md"))
    export_path = args.export_file or cfg.get("export_file_path", os.path.join(_opt_out, "optimizer", "export_score.json"))
    export_config = build_export_config(export_path, cfg)
    print("=" * 60)
    print("DSPy 生成器优化")
    print("=" * 60)
    print(f"  trainset: {args.trainset}")
    print(f"  卡片输出: {output_cards}")
    print(f"  导出文件（读取分数）: {export_path}\n")
    model_type = DEFAULT_MODEL_TYPE
    api_key = DOUBAO_API_KEY if model_type == "doubao" else DEEPSEEK_API_KEY
    try:
        run_optimize_dspy(
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
