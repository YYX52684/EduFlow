#!/usr/bin/env python3
"""
DSPy 优化器统一入口：从 trainset.json 加载样本，按评分优化卡片生成能力。
API Key 与模型选择与其它功能一致（doubao / deepseek）。

使用:
  python run_optimizer.py
  python run_optimizer.py --workspace 编译原理   # 使用 workspaces/编译原理/output/optimizer/
  python run_optimizer.py --trainset output/optimizer/trainset.json --model doubao --optimizer bootstrap
"""
import os
import sys
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    DEFAULT_MODEL_TYPE,
    DOUBAO_API_KEY,
    DEEPSEEK_API_KEY,
    DSPY_OPTIMIZER_CONFIG,
    OPTIMIZER_OUTPUT_DIR,
)
from api.workspace import get_workspace_dirs
from generators.trainset_builder import load_trainset
from generators.dspy_optimizer import run_optimize_dspy


def main():
    parser = argparse.ArgumentParser(
        description="运行 DSPy 优化器（从 trainset JSON 加载，支持 doubao/deepseek）"
    )
    parser.add_argument(
        "--workspace", "-w",
        metavar="NAME",
        default=None,
        help="项目名，与 Web 统一：默认路径为 workspaces/<NAME>/output/optimizer/；不指定则用根目录 output/optimizer",
    )
    parser.add_argument(
        "--trainset",
        default=None,
        help="trainset JSON 路径（默认随 --workspace 或 output/optimizer/trainset.json）",
    )
    parser.add_argument(
        "--model",
        choices=["doubao", "deepseek"],
        default=None,
        help=f"模型（默认: {DEFAULT_MODEL_TYPE}）",
    )
    parser.add_argument(
        "--optimizer",
        choices=["bootstrap", "mipro"],
        default="bootstrap",
        help="优化器类型",
    )
    parser.add_argument(
        "--cards-output",
        default=None,
        help="生成卡片输出路径（默认随 --workspace 或 output/optimizer/cards_for_eval.md）",
    )
    parser.add_argument(
        "--export",
        default=None,
        help="外部评估导出文件路径（默认随 --workspace 或 output/optimizer/export_score.json）",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Bootstrap 轮数（默认从 config）",
    )
    parser.add_argument(
        "--max-demos",
        type=int,
        default=None,
        help="Bootstrap 最大示例数（默认从 config）",
    )
    parser.add_argument(
        "--auto-eval",
        action="store_true",
        default=True,
        help="闭环模式（默认开启）：以仿真+评估替代外部平台人工评估",
    )
    parser.add_argument(
        "--no-auto-eval",
        dest="auto_eval",
        action="store_false",
        help="禁用闭环模式，使用外部评估",
    )
    parser.add_argument(
        "--persona",
        default="excellent",
        help="闭环模式下的学生人设（默认: excellent）",
    )
    args = parser.parse_args()

    model_type = args.model or DEFAULT_MODEL_TYPE
    if model_type == "doubao" and not DOUBAO_API_KEY:
        print("错误: 未配置豆包 API Key（.env 中 LLM_API_KEY）")
        sys.exit(1)
    if model_type != "doubao" and not DEEPSEEK_API_KEY:
        print("错误: 未配置 DEEPSEEK_API_KEY")
        sys.exit(1)

    # 统一目录：--workspace 时用 workspaces/<项目名>/output/optimizer/
    if args.workspace:
        _, _out, _ = get_workspace_dirs(args.workspace.strip())
        _opt_dir = os.path.join(_out, "optimizer")
    else:
        _opt_dir = OPTIMIZER_OUTPUT_DIR  # 已是 .../output/optimizer

    trainset_path = args.trainset or os.path.join(_opt_dir, "trainset.json")
    trainset_path = os.path.abspath(trainset_path)
    if not os.path.isfile(trainset_path):
        print(f"错误: trainset 文件不存在: {trainset_path}")
        print("  请先导入剧本（解析时会自动生成 trainset），或使用 --build-trainset 构建。")
        sys.exit(1)

    cfg = DSPY_OPTIMIZER_CONFIG
    cards_path = args.cards_output or cfg.get("cards_output_path") or os.path.join(_opt_dir, "cards_for_eval.md")
    export_path = args.export or cfg.get("export_file_path") or os.path.join(_opt_dir, "export_score.json")
    cards_path = os.path.abspath(cards_path)
    export_path = os.path.abspath(export_path)
    os.makedirs(os.path.dirname(cards_path) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(export_path) or ".", exist_ok=True)

    trainset = load_trainset(trainset_path)
    if not trainset:
        print("错误: trainset 为空")
        sys.exit(1)

    print("=" * 60)
    print("DSPy 优化器")
    print("=" * 60)
    print(f"  trainset: {trainset_path} ({len(trainset)} 条)")
    print(f"  模型: {model_type}")
    print(f"  优化器: {args.optimizer}")
    if args.auto_eval:
        print(f"  闭环模式: 是 (persona={args.persona})")
    print(f"  卡片输出: {cards_path}")
    print(f"  评估导出: {export_path}")
    print("  预计耗时: 闭环模式约 15–60 分钟（取决于 trainset 与轮数）")
    print()

    def _progress_cb(current: int, total: int, message: str):
        pct = min(100, int(100 * current / max(1, total)))
        bar_len = 30
        filled = int(bar_len * current / max(1, total))
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r[{bar}] {pct}% - {message}", end="", flush=True)

    export_config = {
        "parser": cfg.get("parser", "json"),
        "json_score_key": cfg.get("json_score_key", "total_score"),
    }

    try:
        compiled = run_optimize_dspy(
            trainset_path=trainset_path,
            devset_path=None,
            output_cards_path=cards_path,
            export_path=export_path,
            export_config=export_config,
            optimizer_type=args.optimizer,
            api_key=DOUBAO_API_KEY if model_type == "doubao" else DEEPSEEK_API_KEY,
            model_type=model_type,
            max_rounds=args.max_rounds or cfg.get("max_rounds", 1),
            max_bootstrapped_demos=args.max_demos or cfg.get("max_bootstrapped_demos", 4),
            use_auto_eval=args.auto_eval,
            persona_id=args.persona,
            progress_callback=_progress_cb if args.auto_eval else None,
        )
        if args.auto_eval:
            print()
        if args.auto_eval:
            print("[OK] 闭环优化完成。每轮已自动运行仿真+评估。")
        else:
            print("[OK] 优化完成。请使用外部平台对生成的卡片进行评估，并将结果导出到上述 export 路径后继续迭代。")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ERR] 优化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
