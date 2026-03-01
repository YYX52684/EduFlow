# -*- coding: utf-8 -*-
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Depends
from pydantic import BaseModel
from parsers import get_parser_for_extension
from generators import ContentSplitter
from generators.trainset_builder import write_trainset_for_document
from api.routes.auth import require_workspace_owned
from api.workspace import get_project_dirs, resolve_workspace_path
from api.routes.llm_config import get_llm_config, require_llm_config
from api.exceptions import BadRequestError, LLMError

router = APIRouter()


def _parse_file_to_content(path: str, suffix: str) -> str:
    """根据路径与扩展名解析文件，返回纯文本内容。"""
    parser = get_parser_for_extension(suffix)
    return parser(path)


def _stages_to_trainset_format(stages: list) -> list:
    """将 ContentSplitter 的 stages 转为 trainset 所需格式。保留 interaction_rounds 供卡片生成使用。"""
    return [
        {
            "id": s.get("id"),
            "title": s.get("title"),
            "description": s.get("description"),
            "role": s.get("role"),
            "task": s.get("task"),
            "key_points": s.get("key_points", []),
            "content_excerpt": s.get("content_excerpt") or "",
            "interaction_rounds": s.get("interaction_rounds"),
        }
        for s in stages
    ]


def _write_trainset_lib(
    workspace_id: str,
    full_content: str,
    stages_for_trainset: list,
    source_file: str,
) -> Optional[str]:
    """
    将当前文档写入工作区 trainset 库：output/trainset_lib/{原文档名}_trainset.json。
    任何异常不抛出，返回 None；成功返回相对路径（如 output/trainset_lib/xxx_trainset.json）。
    """
    if not workspace_id or not stages_for_trainset:
        return None
    try:
        _, output_dir, _ = get_project_dirs(workspace_id)
        return write_trainset_for_document(
            output_dir,
            source_file,
            full_content,
            stages_for_trainset,
            source_file=source_file,
        )
    except Exception:
        return None


@router.post("/upload")
async def upload_and_analyze(file: UploadFile = File(...), workspace_id: str = Depends(require_workspace_owned)):
    """上传剧本文件，解析内容并分析结构；需登录且写入当前用户工作区。"""
    suffix = os.path.splitext(file.filename or "")[1].lower() or ".md"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        path = tmp.name
    try:
        full_content = _parse_file_to_content(path, suffix)
        llm = get_llm_config(workspace_id) if workspace_id else {}
        splitter = ContentSplitter(
            api_key=llm.get("api_key") or None,
            base_url=llm.get("base_url") or None,
            model=llm.get("model") or None,
        )
        result = splitter.analyze(full_content)
        stages = result.get("stages", [])
        stages_for_trainset = _stages_to_trainset_format(stages)
        out = {
            "filename": file.filename,
            "full_content_length": len(full_content),
            "stages_count": len(stages),
            "stages": stages_for_trainset,
            "full_content": full_content,
        }
        if result.get("_truncated_note"):
            out["truncated_note"] = result["_truncated_note"]
        trainset_path = _write_trainset_lib(
            workspace_id, full_content, stages_for_trainset, file.filename or ""
        )
        if trainset_path is not None:
            out["trainset_path"] = trainset_path
            out["trainset_count"] = 1
        return out
    except Exception as e:
        raise LLMError("上传解析或分析失败", details={"reason": str(e)})
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


class AnalyzePathRequest(BaseModel):
    path: str  # 相对工作区，如 input/示例剧本.md


@router.post("/analyze-path")
def analyze_by_path(req: AnalyzePathRequest, workspace_id: str = Depends(require_workspace_owned)):
    """根据当前工作区 input 内文件路径解析并分析结构。"""
    path = req.path.strip().replace("\\", "/")
    if path.startswith("/") or ".." in path or not path.startswith("input/"):
        raise BadRequestError("路径不合法，应为 input/ 下路径", details={"path": path})
    full = resolve_workspace_path(workspace_id, path, kind="input", must_exist=True)
    suffix = os.path.splitext(full)[1].lower()
    try:
        full_content = _parse_file_to_content(full, suffix)
    except ValueError as e:
        raise BadRequestError(str(e), details={"path": req.path})
    try:
        llm = require_llm_config(workspace_id)
        splitter = ContentSplitter(
            api_key=llm.get("api_key") or None,
            base_url=llm.get("base_url") or None,
            model=llm.get("model") or None,
        )
        result = splitter.analyze(full_content)
        stages = result.get("stages", [])
        stages_for_trainset = _stages_to_trainset_format(stages)
        out = {
            "filename": os.path.basename(full),
            "path": path,
            "full_content_length": len(full_content),
            "stages_count": len(stages),
            "stages": stages_for_trainset,
            "full_content": full_content,
        }
        if result.get("_truncated_note"):
            out["truncated_note"] = result["_truncated_note"]
        trainset_path = _write_trainset_lib(
            workspace_id, full_content, stages_for_trainset, os.path.basename(full)
        )
        if trainset_path is not None:
            out["trainset_path"] = trainset_path
            out["trainset_count"] = 1
        return out
    except Exception as e:
        raise LLMError("按路径分析失败", details={"reason": str(e)})
