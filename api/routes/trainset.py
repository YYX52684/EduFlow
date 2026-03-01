# -*- coding: utf-8 -*-
"""
Trainset 构建与校验 API：供 DSPy 优化前使用。
路径均相对当前工作区（input/、output/）。
支持 trainset 库（output/trainset_lib/）的列表与删除。
"""
import os
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from api.routes.auth import require_workspace_owned
from api.workspace import (
    WorkspaceManager,
    get_project_dirs,
    resolve_input_path,
    resolve_output_path,
    resolve_workspace_path,
    list_dir_files_with_mtime,
)
from api.routes.llm_config import require_llm_config
from api.exceptions import BadRequestError, ConfigError, NotFoundError, LLMError
from generators.trainset_builder import (
    build_trainset_from_path,
    save_trainset,
    load_trainset,
    check_trainset_file,
)

TRAINSET_LIB_SUBDIR = "trainset_lib"


class BuildTrainsetRequest(BaseModel):
    input_path: str  # 如 input/ 或 input/郑州轻工业大学《编译原理》
    output_path: str = "output/optimizer/trainset.json"


@router.post("/build")
def build_trainset(req: BuildTrainsetRequest, workspace_id: str = Depends(require_workspace_owned)):
    """从剧本文件或目录构建 trainset，保存为 JSON。使用工作区 LLM 配置。"""
    llm = require_llm_config(workspace_id)
    wm = WorkspaceManager(workspace_id)
    abs_input = wm.resolve_input_path(req.input_path)
    if not os.path.exists(abs_input):
        raise NotFoundError("数据来源不存在", details={"path": req.input_path})
    abs_output = wm.resolve_output_path(req.output_path)
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
def validate_trainset(req: ValidateTrainsetRequest, workspace_id: str = Depends(require_workspace_owned)):
    """校验 trainset JSON 结构与评估标准对齐。"""
    wm = WorkspaceManager(workspace_id)
    abs_path = wm.resolve_output_path(req.trainset_path, must_exist=True)
    try:
        valid, messages = check_trainset_file(abs_path, strict=False, check_eval_alignment=True)
    except Exception as e:
        raise LLMError("校验 trainset 失败", details={"reason": str(e)})
    return {"valid": valid, "messages": messages}


@router.get("/list")
def list_trainset_lib(workspace_id: str = Depends(require_workspace_owned)):
    """
    列出当前工作区 trainset 库（output/trainset_lib/）下所有 .json 文件。
    返回 path（相对 output）、name、mtime，按 mtime 降序（最新在前）。
    """
    _, output_dir, _ = get_project_dirs(workspace_id)
    lib_dir = os.path.join(output_dir, TRAINSET_LIB_SUBDIR)
    path_prefix = f"output/{TRAINSET_LIB_SUBDIR}/"
    if not os.path.isdir(lib_dir):
        return {"files": []}
    files = list_dir_files_with_mtime(lib_dir, path_prefix, allowed_ext={".json"})
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return {"files": files}


class DeleteTrainsetRequest(BaseModel):
    path: str  # 相对 output，如 output/trainset_lib/xxx_trainset.json


@router.delete("/delete")
def delete_trainset(req: DeleteTrainsetRequest, workspace_id: str = Depends(require_workspace_owned)):
    """删除 trainset 库中指定文件；path 必须落在 output/trainset_lib/ 下。"""
    path = (req.path or "").strip().replace("\\", "/")
    if not path.startswith("output/") and not path.startswith(f"{TRAINSET_LIB_SUBDIR}/"):
        path = f"output/{path}" if path else ""
    if not path or f"/{TRAINSET_LIB_SUBDIR}/" not in path and not path.startswith(f"output/{TRAINSET_LIB_SUBDIR}"):
        raise BadRequestError("仅允许删除 output/trainset_lib/ 下的文件", details={"path": path})
    _, output_dir, _ = get_project_dirs(workspace_id)
    abs_path = resolve_output_path(workspace_id, path, must_exist=True)
    lib_dir = os.path.join(output_dir, TRAINSET_LIB_SUBDIR)
    lib_dir_abs = os.path.normpath(lib_dir)
    abs_path_norm = os.path.normpath(abs_path)
    if not (abs_path_norm == lib_dir_abs or abs_path_norm.startswith(lib_dir_abs + os.sep)):
        raise BadRequestError("路径不在 trainset 库内", details={"path": path})
    try:
        os.remove(abs_path)
    except OSError as e:
        raise LLMError("删除失败", details={"path": path, "reason": str(e)})
    return {"deleted": path}
