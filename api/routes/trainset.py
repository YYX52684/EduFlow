# -*- coding: utf-8 -*-
"""
Trainset 构建与校验 API：供 DSPy 优化前使用。
路径均相对当前工作区（input/、output/）。
"""
import os
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from api.workspace import get_workspace_id, get_project_dirs, resolve_workspace_path
from api.routes.llm_config import require_llm_config
from api.exceptions import BadRequestError, ConfigError, NotFoundError, LLMError
from generators.trainset_builder import (
    build_trainset_from_path,
    save_trainset,
    load_trainset,
    check_trainset_file,
)


def _resolve_input_path(workspace_id: str, relative_path: str) -> str:
    path = relative_path.strip().replace("\\", "/").lstrip("/")
    if not path.startswith("input/"):
        path = "input/" + path if path != "input" else "input"
    return resolve_workspace_path(workspace_id, path, kind="input")


def _resolve_output_path(workspace_id: str, relative_path: str) -> str:
    path = relative_path.strip().replace("\\", "/").lstrip("/")
    if not path.startswith("output/"):
        path = "output/" + path
    return resolve_workspace_path(workspace_id, path, kind="output")


class BuildTrainsetRequest(BaseModel):
    input_path: str  # 如 input/ 或 input/郑州轻工业大学《编译原理》
    output_path: str = "output/optimizer/trainset.json"


@router.post("/build")
def build_trainset(req: BuildTrainsetRequest, workspace_id: str = Depends(get_workspace_id)):
    """从剧本文件或目录构建 trainset，保存为 JSON。使用工作区 LLM 配置。"""
    llm = require_llm_config(workspace_id)
    abs_input = _resolve_input_path(workspace_id, req.input_path)
    if not os.path.exists(abs_input):
        raise NotFoundError("数据来源不存在", details={"path": req.input_path})
    abs_output = _resolve_output_path(workspace_id, req.output_path)
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
        raise LLMError("构建 trainset 失败", details={"reason": str(e)})
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
    abs_path = resolve_workspace_path(workspace_id, req.trainset_path, kind="output", must_exist=True)
    try:
        valid, messages = check_trainset_file(abs_path, strict=False, check_eval_alignment=True)
    except Exception as e:
        raise LLMError("校验 trainset 失败", details={"reason": str(e)})
    return {"valid": valid, "messages": messages}
