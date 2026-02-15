# -*- coding: utf-8 -*-
"""
闭环优化 API：生成 → 仿真 → 评估 → 导出

提供一键式闭环流水线，将评估报告写入 output/optimizer/export_score.json，
供 DSPy 优化器直接使用，无需外部平台人工评估。
"""
import os
import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from api.workspace import get_workspace_id, get_project_dirs, resolve_workspace_path
from api.exceptions import LLMError
from api.routes.llm_config import require_llm_config
from api.routes.evaluate import _write_export_files
from generators.closed_loop import run_simulate_and_evaluate


class ClosedLoopRequest(BaseModel):
    """闭环运行请求"""
    cards_path: str  # 卡片文件路径，如 output/cards_output_xxx.md
    persona_id: str = "excellent"
    save_to_export: bool = True  # 是否保存为 output/optimizer/export_score.json 供优化器使用


@router.post("/run")
def run_closed_loop(req: ClosedLoopRequest, workspace_id: str = Depends(get_workspace_id)):
    """
    运行闭环：仿真 + 评估，可选保存为优化器导出文件。

    流程：加载卡片 → 运行仿真（LLM 扮演学生）→ 评估对话质量 → 可选写入 export_score.json

    返回评估报告及可选 saved_export_path。若 save_to_export=True，优化器可直接使用该导出文件。
    """
    md_path = resolve_workspace_path(workspace_id, req.cards_path, kind="output", must_exist=True)

    llm = require_llm_config(workspace_id)
    api_key = llm.get("api_key") or ""
    base_url = (llm.get("base_url") or "").rstrip("/")
    model_name = llm.get("model") or ""
    model_type = (llm.get("model_type") or "deepseek").lower()

    api_url = f"{base_url}/chat/completions"
    sim_config = {"api_url": api_url, "api_key": api_key, "model": model_name}

    _, output_dir, _ = get_project_dirs(workspace_id)
    sim_output = os.path.join(output_dir, "simulator_output", "closed_loop")

    try:
        log, report = run_simulate_and_evaluate(
            cards_path=md_path,
            output_dir=sim_output,
            api_key=api_key,
            model_type=model_type,
            persona_id=req.persona_id,
            save_logs=True,
            verbose=False,
            api_url=api_url,
            model_name=model_name,
        )
    except Exception as e:
        raise LLMError("闭环运行失败", details={"reason": str(e)})

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
