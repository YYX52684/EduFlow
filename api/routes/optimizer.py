# -*- coding: utf-8 -*-
"""
DSPy 优化 API：使用 trainset 与外部评估导出文件运行 BootstrapFewShot / MIPRO。
路径均相对当前工作区。
支持 /run 阻塞返回 与 /run-stream SSE 流式进度。
"""
import os
import json
import threading
import queue
import asyncio
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from config import DSPY_OPTIMIZER_CONFIG
from generators.dspy_optimizer import build_export_config, run_optimize_dspy
from api.routes.auth import require_workspace_owned
from api.workspace import get_project_dirs, resolve_output_path
from api.routes.llm_config import require_llm_config
from api.exceptions import BadRequestError, ConfigError, NotFoundError, LLMError

try:
    from generators import DSPY_AVAILABLE
except Exception:
    DSPY_AVAILABLE = False


class OptimizeRequest(BaseModel):
    trainset_path: str = "output/optimizer/trainset.json"
    devset_path: Optional[str] = None
    cards_output_path: Optional[str] = None  # 默认 output/optimizer/cards_for_eval.md
    export_path: Optional[str] = None  # 默认 output/optimizer/export_score.json
    optimizer_type: str = "bootstrap"  # bootstrap | mipro
    model_type: Optional[str] = None  # doubao | deepseek，默认与 DEFAULT_MODEL_TYPE 一致
    max_rounds: Optional[int] = None
    use_auto_eval: bool = True  # 闭环模式（默认）：仿真+评估替代外部评估
    persona_id: str = "excellent"  # 闭环模式下的学生人设


def _run_optimizer(req: OptimizeRequest, workspace_id: str, progress_callback=None) -> dict:
    """核心逻辑：校验、解析路径、调用 run_optimize_dspy。返回 result 字典。"""
    if not DSPY_AVAILABLE:
        raise ConfigError("未安装 dspy-ai，请运行 pip install dspy-ai")
    llm = require_llm_config(workspace_id)
    model_type = (req.model_type or llm.get("model_type") or "deepseek").lower()
    cfg = DSPY_OPTIMIZER_CONFIG

    trainset_abs = resolve_output_path(workspace_id, req.trainset_path)
    if not os.path.isfile(trainset_abs):
        raise NotFoundError(
            "trainset 文件不存在。请确认已在该项目下构建 trainset 并保存到 output/optimizer/trainset.json",
            details={"path": req.trainset_path},
        )
    cards_path = req.cards_output_path or "output/optimizer/cards_for_eval.md"
    export_path_rel = req.export_path or "output/optimizer/export_score.json"
    cards_abs = resolve_output_path(workspace_id, cards_path)
    export_abs = resolve_output_path(workspace_id, export_path_rel)
    os.makedirs(os.path.dirname(cards_abs) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(export_abs) or ".", exist_ok=True)

    devset_abs = None
    if req.devset_path:
        devset_abs = resolve_output_path(workspace_id, req.devset_path)
        if not os.path.isfile(devset_abs):
            raise NotFoundError("devset 文件不存在", details={"path": req.devset_path})

    export_config = build_export_config(export_abs, cfg)
    if req.optimizer_type not in ("bootstrap", "mipro"):
        raise BadRequestError("optimizer_type 须为 bootstrap 或 mipro", details={"value": req.optimizer_type})

    kwargs = {
        "trainset_path": trainset_abs,
        "devset_path": devset_abs,
        "output_cards_path": cards_abs,
        "export_path": export_abs,
        "export_config": export_config,
        "optimizer_type": req.optimizer_type,
        "api_key": llm["api_key"],
        "model_type": model_type,
        "max_rounds": req.max_rounds or cfg.get("max_rounds", 1),
        "max_bootstrapped_demos": cfg.get("max_bootstrapped_demos", 4),
        "use_auto_eval": req.use_auto_eval,
        "persona_id": req.persona_id,
    }
    if progress_callback is not None:
        kwargs["progress_callback"] = progress_callback

    run_optimize_dspy(**kwargs)

    hint = (
        "闭环模式已完成，每轮已自动仿真+评估。"
        if req.use_auto_eval
        else f"请使用外部平台对 {cards_path} 进行评估，并将结果导出到 {export_path_rel} 后继续迭代。"
    )
    final_report_rel = "output/optimizer/closed_loop_final_report.md"
    if not req.use_auto_eval:
        final_report_abs = resolve_output_path(workspace_id, final_report_rel)
        os.makedirs(os.path.dirname(final_report_abs) or ".", exist_ok=True)
        with open(final_report_abs, "w", encoding="utf-8") as f:
            f.write("# 优化运行报告\n\n本次使用外部评估。\n\n分数文件：`" + export_path_rel + "`\n")
    out = {
        "message": "优化完成。优化后的程序已返回（后续可接入保存/加载）。",
        "cards_output_path": cards_path,
        "export_path": export_path_rel,
        "use_auto_eval": req.use_auto_eval,
        "hint": hint,
        "evaluation_report_path": final_report_rel,
    }
    return out


@router.post("/run")
def run_optimizer(req: OptimizeRequest, workspace_id: str = Depends(require_workspace_owned)):
    """运行 DSPy 优化。耗时可较长，完成后返回优化结果说明。"""
    try:
        return _run_optimizer(req, workspace_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise LLMError("优化运行失败", details={"reason": str(e)})


@router.post("/run-stream")
async def run_optimizer_stream(req: OptimizeRequest, workspace_id: str = Depends(require_workspace_owned)):
    """运行 DSPy 优化，通过 SSE 流式返回进度。闭环模式约 15–60 分钟（取决于 trainset 与轮数）。"""
    if not DSPY_AVAILABLE:
        raise ConfigError("未安装 dspy-ai，请运行 pip install dspy-ai")
    require_llm_config(workspace_id)
    # 提前校验路径，避免线程内再抛
    trainset_abs = resolve_output_path(workspace_id, req.trainset_path)
    if not os.path.isfile(trainset_abs):
        raise NotFoundError("trainset 文件不存在", details={"path": req.trainset_path})

    q = queue.Queue()

    def run():
        try:
            def progress_cb(current: int, total: int, message: str):
                q.put(("progress", {"current": current, "total": total, "message": message}))

            result = _run_optimizer(req, workspace_id, progress_callback=progress_cb)
            result["message"] = "优化完成。"
            q.put(("done", result))
        except Exception as e:
            import traceback
            traceback.print_exc()
            q.put(("error", str(e)))

    th = threading.Thread(target=run, daemon=True)
    th.start()

    async def event_stream():
        yield f"event: progress\ndata: {json.dumps({'current': 0, 'total': 1, 'percent': 0, 'message': '正在加载模型与 trainset…'}, ensure_ascii=False)}\n\n"
        while True:
            try:
                typ, payload = q.get(timeout=0.2)
            except queue.Empty:
                await asyncio.sleep(0.1)
                continue
            if typ == "progress":
                pct = int(100 * payload["current"] / max(1, payload["total"]))
                data = json.dumps({**payload, "percent": pct}, ensure_ascii=False)
                yield f"event: progress\ndata: {data}\n\n"
            elif typ == "done":
                yield f"event: done\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                break
            elif typ == "error":
                yield f"event: error\ndata: {json.dumps({'detail': payload}, ensure_ascii=False)}\n\n"
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
