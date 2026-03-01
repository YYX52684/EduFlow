#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSPy 优化器统一入口：从 trainset.json 加载样本，按评分优化卡片生成能力。
API Key 与模型选择与其它功能一致（doubao / deepseek）。

使用:
  python run_optimizer.py
  python run_optimizer.py --workspace 编译原理   # 使用 workspaces/编译原理/output/optimizer/
  python run_optimizer.py --trainset output/optimizer/trainset.json --model doubao --optimizer bootstrap
"""
import io
import os
import sys
import argparse
import json
import hashlib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows 下强制 stdout/stderr 使用 UTF-8，避免进度条等 Unicode 字符（如 ░）触发 GBK 编码错误
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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
        help=f"模型（默认: {DEFAULT_MODEL_TYPE}，推荐使用豆包 doubao）",
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
        help="闭环评估报告导出文件路径（默认随 --workspace 或 output/optimizer/export_score.json）",
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
        "--persona",
        default="excellent",
        help="闭环模式下的学生人设（默认: excellent）",
    )
    parser.add_argument(
        "--course-id",
        default=None,
        help="按课程 ID 选择 trainset_<course-id>.json（与 --workspace 联用时，位于对应工作区 output/optimizer/ 下）",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="禁用课程级缓存：即使 trainset 未变化也强制重新优化",
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

    # trainset 选择逻辑：
    # 1) 显式指定 --trainset 时优先；
    # 2) 其后若指定 --course-id，则使用 trainset_<course-id>.json；
    # 3) 否则退化为默认的 trainset.json。
    if args.trainset:
        trainset_path = args.trainset
        course_id = None
    else:
        course_id = (args.course_id or "").strip() or None
        if course_id:
            trainset_path = os.path.join(_opt_dir, f"trainset_{course_id}.json")
        else:
            trainset_path = os.path.join(_opt_dir, "trainset.json")
    trainset_path = os.path.abspath(trainset_path)
    if not os.path.isfile(trainset_path):
        print(f"错误: trainset 文件不存在: {trainset_path}")
        print("  请先导入剧本（解析时会自动生成 trainset），或使用 --build-trainset 构建。")
        sys.exit(1)

    cfg = DSPY_OPTIMIZER_CONFIG
    cards_path = args.cards_output or cfg.get("cards_output_path") or os.path.join(_opt_dir, "cards_for_eval.md")
    export_path = args.export or os.path.join(_opt_dir, "export_score.json")
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
    print(f"  闭环模式: 是 (persona={args.persona})")
    print(f"  卡片输出: {cards_path}")
    print(f"  评估报告导出: {export_path}")
    print("  预计耗时: 闭环模式约 15–60 分钟（取决于 trainset 与轮数）")
    print()

    # 课程级缓存：仅在按 course_id 运行且未显式关闭缓存时生效
    if course_id and not args.no_cache:
        cache_path = os.path.join(os.path.dirname(trainset_path), f"cache_{course_id}.json")
        try:
            with open(trainset_path, "rb") as f:
                trainset_bytes = f.read()
            trainset_hash = hashlib.sha256(trainset_bytes).hexdigest()
        except Exception:
            trainset_hash = None

        if trainset_hash and os.path.isfile(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                if cache_data.get("trainset_hash") == trainset_hash:
                    print(f"[CACHE] 课程 {course_id} 的 trainset 未变化，本次命中缓存，跳过优化。")
                    print("        若需强制重新优化，请添加 --no-cache 参数。")
                    return
            except Exception:
                pass

    def _progress_cb(current: int, total: int, message: str):
        pct = min(100, int(100 * current / max(1, total)))
        bar_len = 30
        filled = int(bar_len * current / max(1, total))
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r[{bar}] {pct}% - {message}", end="", flush=True)

    try:
        compiled = run_optimize_dspy(
            trainset_path=trainset_path,
            devset_path=None,
            output_cards_path=cards_path,
            export_path=export_path,
            export_config=None,
            optimizer_type=args.optimizer,
            api_key=DOUBAO_API_KEY if model_type == "doubao" else DEEPSEEK_API_KEY,
            model_type=model_type,
            max_rounds=args.max_rounds or cfg.get("max_rounds", 1),
            max_bootstrapped_demos=args.max_demos or cfg.get("max_bootstrapped_demos", 4),
            persona_id=args.persona,
            progress_callback=_progress_cb,
        )
        print()
        print("[OK] 闭环优化完成。每轮已自动运行仿真+评估。")

        # 写入课程级缓存元数据，便于下次快速判断是否需要重跑
        if course_id:
            cache_path = os.path.join(os.path.dirname(trainset_path), f"cache_{course_id}.json")
            try:
                with open(trainset_path, "rb") as f:
                    trainset_bytes = f.read()
                trainset_hash = hashlib.sha256(trainset_bytes).hexdigest()
                cache_payload = {
                    "course_id": course_id,
                    "trainset_path": os.path.abspath(trainset_path),
                    "trainset_hash": trainset_hash,
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(cache_payload, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ERR] 优化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
