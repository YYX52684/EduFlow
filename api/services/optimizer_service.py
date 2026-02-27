import os
from typing import Callable, Optional

from config import DSPY_OPTIMIZER_CONFIG
from generators.dspy_optimizer import run_optimize_dspy
from api.workspace import WorkspaceManager
from api.routes.llm_config import require_llm_config
from api.exceptions import BadRequestError, ConfigError, NotFoundError

from api.schemas.optimizer import OptimizeRequest


ProgressCallback = Callable[[int, int, str], None]


def run_optimizer_core(
    req: OptimizeRequest,
    workspace_id: str,
    progress_callback: Optional[ProgressCallback] = None,
) -> dict:
    """核心优化流程：校验、解析路径、调用 DSPy 优化器并返回结果字典。"""
    try:
        from generators import DSPY_AVAILABLE  # type: ignore[attr-defined]
    except Exception:
        DSPY_AVAILABLE = False  # type: ignore[assignment]

    if not DSPY_AVAILABLE:
        raise ConfigError("未安装 dspy-ai，请运行 pip install dspy-ai")

    llm = require_llm_config(workspace_id)
    wm = WorkspaceManager(workspace_id)
    # 优先使用请求 / 工作区配置中的 model_type，默认退回豆包
    model_type = (req.model_type or llm.get("model_type") or "doubao").lower()
    cfg = DSPY_OPTIMIZER_CONFIG

    trainset_abs = wm.resolve_output_path(req.trainset_path)
    if not os.path.isfile(trainset_abs):
        raise NotFoundError(
            "trainset 文件不存在。请确认已在该项目下构建 trainset 并保存到 output/optimizer/trainset.json",
            details={"path": req.trainset_path},
        )

    cards_path = req.cards_output_path or "output/optimizer/cards_for_eval.md"
    # 闭环模式下，export_path 作为评估结果导出文件（JSON），供前端查看与分析
    export_path_rel = req.export_path or "output/optimizer/export_score.json"
    cards_abs = wm.resolve_output_path(cards_path)
    export_abs = wm.resolve_output_path(export_path_rel)

    os.makedirs(os.path.dirname(cards_abs) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(export_abs) or ".", exist_ok=True)

    devset_abs = None
    if req.devset_path:
        devset_abs = wm.resolve_output_path(req.devset_path)
        if not os.path.isfile(devset_abs):
            raise NotFoundError("devset 文件不存在", details={"path": req.devset_path})

    if req.optimizer_type not in ("bootstrap", "mipro"):
        raise BadRequestError(
            "optimizer_type 须为 bootstrap 或 mipro",
            details={"value": req.optimizer_type},
        )

    kwargs = {
        "trainset_path": trainset_abs,
        "devset_path": devset_abs,
        "output_cards_path": cards_abs,
        "export_path": export_abs,
        "optimizer_type": req.optimizer_type,
        "api_key": llm["api_key"],
        "model_type": model_type,
        "max_rounds": req.max_rounds or cfg.get("max_rounds", 1),
        "max_bootstrapped_demos": cfg.get("max_bootstrapped_demos", 4),
        "persona_id": req.persona_id,
    }
    if progress_callback is not None:
        kwargs["progress_callback"] = progress_callback

    run_optimize_dspy(**kwargs)

    hint = "闭环模式已完成，每轮已自动仿真+评估。"
    final_report_rel = "output/optimizer/closed_loop_final_report.md"

    return {
        "message": "优化完成。优化后的程序已返回（后续可接入保存/加载）。",
        "cards_output_path": cards_path,
        "export_path": export_path_rel,
        "use_auto_eval": True,
        "hint": hint,
        "evaluation_report_path": final_report_rel,
    }

