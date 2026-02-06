# -*- coding: utf-8 -*-
"""
DSPy 优化 API：使用 trainset 与外部评估导出文件运行 BootstrapFewShot / MIPRO。
路径均相对当前工作区。
"""
import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from config import DSPY_OPTIMIZER_CONFIG
from api.workspace import get_workspace_id, get_project_dirs
from api.routes.llm_config import get_llm_config

try:
    from generators import DSPY_AVAILABLE
except Exception:
    DSPY_AVAILABLE = False


def _resolve_output_path(workspace_id: str, relative_path: str) -> str:
    path = relative_path.strip().replace("\\", "/").lstrip("/")
    if not path.startswith("output/"):
        path = "output/" + path
    _, output_dir, _ = get_project_dirs(workspace_id)
    sub = path[7:] if path.startswith("output/") else path
    full = os.path.normpath(os.path.join(output_dir, sub))
    base_abs = os.path.normpath(output_dir)
    if not (full == base_abs or full.startswith(base_abs + os.sep)):
        raise HTTPException(status_code=400, detail="路径必须在 output/ 下")
    return full


class OptimizeRequest(BaseModel):
    trainset_path: str = "output/optimizer/trainset.json"
    devset_path: Optional[str] = None
    cards_output_path: Optional[str] = None  # 默认 output/optimizer/cards_for_eval.md
    export_path: Optional[str] = None  # 默认 output/optimizer/export_score.json
    optimizer_type: str = "bootstrap"  # bootstrap | mipro
    model_type: Optional[str] = None  # doubao | deepseek，默认与 DEFAULT_MODEL_TYPE 一致
    max_rounds: Optional[int] = None


@router.post("/run")
def run_optimizer(req: OptimizeRequest, workspace_id: str = Depends(get_workspace_id)):
    """运行 DSPy 优化。耗时可较长，完成后返回优化结果说明。"""
    if not DSPY_AVAILABLE:
        raise HTTPException(status_code=500, detail="未安装 dspy-ai，请运行 pip install dspy-ai")
    llm = get_llm_config(workspace_id)
    if not llm.get("api_key"):
        raise HTTPException(status_code=500, detail="未配置 API Key，请在「设置」中填写并保存")
    model_type = (req.model_type or llm.get("model_type") or "deepseek").lower()

    cfg = DSPY_OPTIMIZER_CONFIG
    trainset_abs = _resolve_output_path(workspace_id, req.trainset_path)
    if not os.path.isfile(trainset_abs):
        raise HTTPException(
            status_code=404,
            detail=f"trainset 文件不存在: {req.trainset_path}（实际查找: {trainset_abs}）。请确认：1) 当前项目名为 {workspace_id}；2) 已在该项目下构建 trainset 并保存到 output/optimizer/trainset.json"
        )

    cards_path = req.cards_output_path or "output/optimizer/cards_for_eval.md"
    export_path_rel = req.export_path or "output/optimizer/export_score.json"
    cards_abs = _resolve_output_path(workspace_id, cards_path)
    export_abs = _resolve_output_path(workspace_id, export_path_rel)
    os.makedirs(os.path.dirname(cards_abs) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(export_abs) or ".", exist_ok=True)

    devset_abs = None
    if req.devset_path:
        devset_abs = _resolve_output_path(workspace_id, req.devset_path)
        if not os.path.isfile(devset_abs):
            raise HTTPException(status_code=404, detail=f"devset 文件不存在: {req.devset_path}")

    _ext = os.path.splitext(export_abs)[1].lower()
    _parser = "md" if _ext in (".md", ".markdown") else cfg.get("parser", "json")
    export_config = {
        "parser": _parser,
        "json_score_key": cfg.get("json_score_key", "total_score"),
        "csv_score_column": cfg.get("csv_score_column"),
    }
    if req.optimizer_type not in ("bootstrap", "mipro"):
        raise HTTPException(status_code=400, detail="optimizer_type 须为 bootstrap 或 mipro")

    try:
        from generators.dspy_optimizer import run_optimize_dspy

        compiled = run_optimize_dspy(
            trainset_path=trainset_abs,
            devset_path=devset_abs,
            output_cards_path=cards_abs,
            export_path=export_abs,
            export_config=export_config,
            optimizer_type=req.optimizer_type,
            api_key=llm["api_key"],
            model_type=model_type,
            max_rounds=req.max_rounds or cfg.get("max_rounds", 1),
            max_bootstrapped_demos=cfg.get("max_bootstrapped_demos", 4),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()  # 输出完整堆栈到控制台，便于排查
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "message": "优化完成。优化后的程序已返回（后续可接入保存/加载）。",
        "cards_output_path": cards_path,
        "export_path": export_path_rel,
        "hint": f"请使用外部平台对 {cards_path} 进行评估，并将结果导出到 {export_path_rel} 后继续迭代。",
    }
