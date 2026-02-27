# -*- coding: utf-8 -*-
"""
DSPy 优化 API。

说明：
- 路由层仅负责参数校验与协议（SSE 事件）；
- 具体业务逻辑委托给 `api.services.optimizer_service`。
- 使用子进程而非线程运行优化器，避免 dspy.settings 的线程局部性冲突（dspy 只能在首次配置的线程中修改）。
"""
import json
import os
import asyncio
import multiprocessing as mp
from queue import Empty as QueueEmpty

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

router = APIRouter()

from api.routes.auth import require_workspace_owned
from api.workspace import resolve_output_path
from api.routes.llm_config import require_llm_config
from api.exceptions import ConfigError, NotFoundError, LLMError
from api.schemas.optimizer import OptimizeRequest
from api.services.optimizer_service import run_optimizer_core

try:
    from generators import DSPY_AVAILABLE
except Exception:
    DSPY_AVAILABLE = False


def _optimizer_worker(req_dict: dict, workspace_id: str, result_queue: mp.Queue) -> None:
    """在子进程中运行优化器，确保 dspy 在进程主线程中配置，避免线程冲突。"""
    req = OptimizeRequest(**req_dict)

    def progress_cb(current: int, total: int, message: str):
        result_queue.put(("progress", {"current": current, "total": total, "message": message}))

    try:
        result = run_optimizer_core(req, workspace_id, progress_callback=progress_cb)
        result["message"] = "优化完成。"
        result_queue.put(("done", result))
    except Exception as e:
        import traceback
        traceback.print_exc()
        result_queue.put(("error", str(e)))


@router.post("/run")
def run_optimizer(req: OptimizeRequest, workspace_id: str = Depends(require_workspace_owned)):
    """运行 DSPy 优化。耗时可较长，完成后返回优化结果说明。使用子进程避免 dspy 线程冲突。"""
    if not DSPY_AVAILABLE:
        raise ConfigError("未安装 dspy-ai，请运行 pip install dspy-ai")
    require_llm_config(workspace_id)
    trainset_abs = resolve_output_path(workspace_id, req.trainset_path)
    if not os.path.isfile(trainset_abs):
        raise NotFoundError("trainset 文件不存在", details={"path": req.trainset_path})

    result_queue = mp.Queue()
    proc = mp.Process(
        target=_optimizer_worker,
        args=(req.model_dump(), workspace_id, result_queue),
    )
    proc.start()
    proc.join()
    typ, payload = result_queue.get()
    if typ == "error":
        raise LLMError("优化运行失败", details={"reason": payload})
    return payload


@router.post("/run-stream")
async def run_optimizer_stream(req: OptimizeRequest, workspace_id: str = Depends(require_workspace_owned)):
    """运行 DSPy 优化，通过 SSE 流式返回进度。闭环模式约 15–60 分钟（取决于 trainset 与轮数）。"""
    if not DSPY_AVAILABLE:
        raise ConfigError("未安装 dspy-ai，请运行 pip install dspy-ai")
    require_llm_config(workspace_id)
    # 提前校验路径，避免进程内再抛
    trainset_abs = resolve_output_path(workspace_id, req.trainset_path)
    if not os.path.isfile(trainset_abs):
        raise NotFoundError("trainset 文件不存在", details={"path": req.trainset_path})

    result_queue = mp.Queue()
    proc = mp.Process(
        target=_optimizer_worker,
        args=(req.model_dump(), workspace_id, result_queue),
    )
    proc.start()

    async def event_stream():
        yield f"event: progress\ndata: {json.dumps({'current': 0, 'total': 1, 'percent': 0, 'message': '正在加载模型与 trainset…'}, ensure_ascii=False)}\n\n"
        loop = asyncio.get_event_loop()
        while proc.is_alive() or not result_queue.empty():
            try:
                typ, payload = await loop.run_in_executor(
                    None, lambda: result_queue.get(timeout=0.2)
                )
            except QueueEmpty:
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
        proc.join(timeout=5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
