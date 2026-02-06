# -*- coding: utf-8 -*-
import json
import os
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

router = APIRouter()

from simulator import evaluate_session
from simulator.evaluator import EvaluatorFactory
from api.workspace import get_workspace_id, get_project_dirs, get_workspace_dirs, resolve_workspace_path


class EvaluateByPathRequest(BaseModel):
    log_path: str
    output_dir: Optional[str] = None
    save_to_export: bool = False  # 保存为 output/optimizer/export_score.json(.md) 供优化器使用


class EvaluateByBodyRequest(BaseModel):
    session_id: str
    dialogue: List[Dict[str, Any]]


def _write_export_files(report, output_dir: str) -> str:
    """将报告写入 output_dir/optimizer/export_score.json 和 .md，返回相对路径如 output/optimizer/export_score.json。"""
    opt_dir = os.path.join(output_dir, "optimizer")
    os.makedirs(opt_dir, exist_ok=True)
    json_path = os.path.join(opt_dir, "export_score.json")
    md_path = os.path.join(opt_dir, "export_score.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report.to_markdown())
    return "output/optimizer/export_score.json"


@router.post("/evaluate")
def evaluate(req: EvaluateByPathRequest, workspace_id: str = Depends(get_workspace_id)):
    """根据当前工作区内会话日志路径评估，返回报告。可选保存为导出文件供优化器使用。"""
    path = resolve_workspace_path(workspace_id, req.log_path, kind="output")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"日志文件不存在: {req.log_path}")
    out_dir = None
    if req.output_dir:
        _, output_dir, _ = get_workspace_dirs(workspace_id)
        out_dir = os.path.join(output_dir, req.output_dir)
    try:
        report = evaluate_session(path, output_dir=out_dir)
        result = report.to_dict()
        if req.save_to_export:
            _, project_output, _ = get_project_dirs(workspace_id)
            export_rel = _write_export_files(report, project_output)
            result["saved_export_path"] = export_rel
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate/from-file")
async def evaluate_from_file(
    workspace_id: str = Depends(get_workspace_id),
    file: UploadFile = File(...),
    save_to_export: bool = Form(False),
):
    """上传会话日志 JSON 文件，直接评估并返回报告。可选保存为导出文件。"""
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="请上传 .json 格式的会话日志")
    try:
        content = await file.read()
        log_data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON 解析失败: {e}")
    dialogue = log_data.get("dialogue", [])
    session_id = log_data.get("session_id", "unknown")
    try:
        evaluator = EvaluatorFactory.create_from_env()
        report = evaluator.evaluate(dialogue, session_id=session_id)
        result = report.to_dict()
        if save_to_export:
            _, project_output, _ = get_project_dirs(workspace_id)
            export_rel = _write_export_files(report, project_output)
            result["saved_export_path"] = export_rel
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate/from-dialogue")
def evaluate_from_dialogue(req: EvaluateByBodyRequest):
    """根据请求体中的 dialogue 与 session_id 直接评估。"""
    try:
        evaluator = EvaluatorFactory.create_from_env()
        report = evaluator.evaluate(req.dialogue, session_id=req.session_id)
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
