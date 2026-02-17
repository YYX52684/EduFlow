# -*- coding: utf-8 -*-
"""
闭环优化 API：生成 → 仿真 → 评估 → 导出

提供一键式闭环流水线，将评估报告写入 output/optimizer/export_score.json，
供 DSPy 优化器直接使用，无需外部平台人工评估。
支持 /run 阻塞返回 与 /run-stream SSE 流式进度（不阻塞页面、可取消）。
"""
import asyncio
import json
import os
import queue
import threading
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from api.routes.auth import require_workspace_owned
from api.workspace import get_project_dirs, resolve_workspace_path
from api.exceptions import LLMError
from api.routes.llm_config import require_llm_config
from api.routes.evaluate import _write_export_files
from generators.closed_loop import run_simulate_and_evaluate


class ClosedLoopRequest(BaseModel):
    """闭环运行请求"""
    cards_path: str  # 卡片文件路径，如 output/cards_output_xxx.md
    persona_id: str = "excellent"
    save_to_export: bool = True  # 是否保存为 output/optimizer/export_score.json 供优化器使用


def _run_closed_loop(req: ClosedLoopRequest, workspace_id: str, progress_callback=None) -> dict:
    """核心逻辑：解析路径、运行仿真+评估，可选写入导出文件。返回 result 字典。"""
    md_path = resolve_workspace_path(workspace_id, req.cards_path, kind="output", must_exist=True)
    llm = require_llm_config(workspace_id)
    api_key = llm.get("api_key") or ""
    base_url = (llm.get("base_url") or "").rstrip("/")
    model_name = llm.get("model") or ""
    model_type = (llm.get("model_type") or "deepseek").lower()
    api_url = f"{base_url}/chat/completions" if base_url else ""
    _, output_dir, _ = get_project_dirs(workspace_id)
    sim_output = os.path.join(output_dir, "simulator_output", "closed_loop")

    kwargs = {
        "cards_path": md_path,
        "output_dir": sim_output,
        "api_key": api_key,
        "model_type": model_type,
        "persona_id": req.persona_id,
        "save_logs": True,
        "verbose": False,
        "api_url": api_url,
        "model_name": model_name,
    }
    if progress_callback is not None:
        kwargs["progress_callback"] = progress_callback

    log, report = run_simulate_and_evaluate(**kwargs)

    result = {
        "session_id": log.session_id,
        "total_score": report.total_score,
        "rating": report.get_rating(),
        "evaluation": report.to_dict(),
    }
    if req.save_to_export:
        _, project_output, _ = get_project_dirs(workspace_id)
        export_rel = _write_export_files(report, project_output)
        result["saved_export_path"] = export_rel
        result["hint"] = f"评估报告已保存到 {export_rel}，可直接运行优化器进行迭代。"
    return result


@router.post("/run")
def run_closed_loop(req: ClosedLoopRequest, workspace_id: str = Depends(require_workspace_owned)):
    """
    运行闭环：仿真 + 评估，可选保存为优化器导出文件。

    流程：加载卡片 → 运行仿真（LLM 扮演学生）→ 评估对话质量 → 可选写入 export_score.json

    返回评估报告及可选 saved_export_path。若 save_to_export=True，优化器可直接使用该导出文件。
    """
    try:
        return _run_closed_loop(req, workspace_id)
    except Exception as e:
        raise LLMError("闭环运行失败", details={"reason": str(e)})


@router.post("/run-stream")
async def run_closed_loop_stream(req: ClosedLoopRequest, workspace_id: str = Depends(require_workspace_owned)):
    """
    流式运行闭环：通过 SSE 推送进度（加载卡片 → 仿真 → 评估 → 导出），
    前端可展示进度并允许用户取消或继续操作其他区域，不阻塞全屏。
    """
    q = queue.Queue()

    def run():
        try:
            def progress_cb(phase: str, message: str):
                q.put(("progress", {"phase": phase, "message": message}))

            result = _run_closed_loop(req, workspace_id, progress_callback=progress_cb)
            q.put(("done", result))
        except Exception as e:
            import traceback
            traceback.print_exc()
            q.put(("error", str(e)))

    th = threading.Thread(target=run, daemon=True)
    th.start()

    async def event_stream():
        yield f"event: progress\ndata: {json.dumps({'phase': 'start', 'message': '正在准备…'}, ensure_ascii=False)}\n\n"
        while True:
            try:
                typ, payload = q.get(timeout=0.2)
            except queue.Empty:
                await asyncio.sleep(0.1)
                continue
            if typ == "progress":
                yield f"event: progress\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
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
