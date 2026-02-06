# -*- coding: utf-8 -*-
"""
Trainset 构建与校验 API：供 DSPy 优化前使用。
路径均相对当前工作区（input/、output/）。
"""
import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from api.workspace import get_workspace_id, get_project_dirs
from api.routes.llm_config import get_llm_config
from generators.trainset_builder import (
    build_trainset_from_path,
    save_trainset,
    load_trainset,
    check_trainset_file,
)


def _resolve_input_path(workspace_id: str, relative_path: str) -> str:
    """将 input/xxx 解析为当前项目工作区内的绝对路径。"""
    path = relative_path.strip().replace("\\", "/").lstrip("/")
    if not path.startswith("input/"):
        path = "input/" + path if path != "input" else "input"
    input_dir, _, _ = get_project_dirs(workspace_id)
    sub = path[6:] if path.startswith("input/") else path  # strip "input/"
    full = os.path.normpath(os.path.join(input_dir, sub))
    if not (full == input_dir or full.startswith(input_dir + os.sep)):
        raise HTTPException(status_code=400, detail="路径必须在 input/ 下")
    return full


def _resolve_output_path(workspace_id: str, relative_path: str) -> str:
    """将 output/xxx 解析为当前项目工作区内的绝对路径。"""
    path = relative_path.strip().replace("\\", "/").lstrip("/")
    if not path.startswith("output/"):
        path = "output/" + path
    _, output_dir, _ = get_project_dirs(workspace_id)
    sub = path[7:] if path.startswith("output/") else path
    full = os.path.normpath(os.path.join(output_dir, sub))
    if not (full == output_dir or full.startswith(output_dir + os.sep)):
        raise HTTPException(status_code=400, detail="路径必须在 output/ 下")
    return full


class BuildTrainsetRequest(BaseModel):
    input_path: str  # 如 input/ 或 input/郑州轻工业大学《编译原理》
    output_path: str = "output/optimizer/trainset.json"


@router.post("/build")
def build_trainset(req: BuildTrainsetRequest, workspace_id: str = Depends(get_workspace_id)):
    """从剧本文件或目录构建 trainset，保存为 JSON。使用工作区 LLM 配置。"""
    llm = get_llm_config(workspace_id)
    if not llm.get("api_key"):
        raise HTTPException(status_code=500, detail="未配置 API Key，请在「设置」中填写并保存")
    abs_input = _resolve_input_path(workspace_id, req.input_path)
    abs_output = _resolve_output_path(workspace_id, req.output_path)
    if not os.path.exists(abs_input):
        raise HTTPException(status_code=404, detail=f"数据来源不存在: {req.input_path}")
    try:
        examples = build_trainset_from_path(
            abs_input,
            api_key=llm["api_key"],
            base_url=llm.get("base_url"),
            model=llm.get("model"),
            verbose=False,
        )
        os.makedirs(os.path.dirname(abs_output) or ".", exist_ok=True)
        save_trainset(examples, abs_output)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "count": len(examples),
        "output_path": req.output_path,
        "message": f"已保存 {len(examples)} 条样本到 {req.output_path}",
    }


class ValidateTrainsetRequest(BaseModel):
    trainset_path: str  # 如 output/optimizer/trainset.json


@router.post("/validate")
def validate_trainset(req: ValidateTrainsetRequest, workspace_id: str = Depends(get_workspace_id)):
    """校验 trainset JSON 结构与评估标准对齐。"""
    abs_path = _resolve_output_path(workspace_id, req.trainset_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail=f"文件不存在: {req.trainset_path}")
    try:
        valid, messages = check_trainset_file(abs_path, strict=False, check_eval_alignment=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"valid": valid, "messages": messages}
