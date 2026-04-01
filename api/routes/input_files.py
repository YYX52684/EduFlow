# -*- coding: utf-8 -*-
"""
input 文件夹：按工作区列出文件、上传并保存到该工作区 input。
支持读取文件内容，供 React 工作区页预览原材料。
"""
import os
from typing import Optional

from fastapi import APIRouter, Request, UploadFile, Depends
from starlette.datastructures import UploadFile as StarletteUploadFile

router = APIRouter()

from api.routes.auth import require_workspace_owned
from api.workspace import (
    get_workspace_dirs,
    list_dir_files,
    save_upload_to_dir,
    resolve_workspace_path,
)
from api.exceptions import BadRequestError, LLMError
from parsers import get_parser_for_extension

# 允许的剧本扩展名
ALLOWED_EXT = {".md", ".docx", ".doc", ".pdf"}

# 放宽 multipart 单 part 大小，避免大文件触发 413/400
MAX_UPLOAD_PART_SIZE = 50 * 1024 * 1024  # 50MB


async def _parse_form(request: Request):
    try:
        return await request.form(max_part_size=MAX_UPLOAD_PART_SIZE)
    except TypeError:
        return await request.form()


def _is_upload_file(value: object) -> bool:
    return isinstance(value, (UploadFile, StarletteUploadFile))


def _read_input_content(full_path: str) -> str:
    suffix = os.path.splitext(full_path)[1].lower()
    parser = get_parser_for_extension(suffix)
    return parser(full_path)


@router.get("/files")
def list_input_files(workspace_id: str = Depends(require_workspace_owned)):
    """列出当前工作区 input 目录下所有文件（递归）。"""
    input_dir, _, _ = get_workspace_dirs(workspace_id)
    files = list_dir_files(input_dir, "input/", allowed_ext=ALLOWED_EXT)
    return {"files": files}


@router.get("/read")
def read_input_file(
    path: str,
    workspace_id: str = Depends(require_workspace_owned),
):
    """读取 input 下指定文件内容；Word/PDF 会先解析为纯文本。"""
    rel_path = (path or "").strip().replace("\\", "/")
    if not rel_path.startswith("input/"):
        rel_path = "input/" + rel_path.lstrip("/")
    full_path = resolve_workspace_path(workspace_id, rel_path, kind="input", must_exist=True)
    try:
        content = _read_input_content(full_path)
    except Exception as e:
        raise LLMError("读取失败", details={"path": rel_path, "reason": str(e)})
    return {"path": rel_path, "content": content}


@router.post("/upload")
async def upload_to_input(
    request: Request,
    workspace_id: str = Depends(require_workspace_owned),
):
    """上传文件并保存到当前工作区 input。返回相对路径如 input/xxx.md。单文件最大约 50MB。"""
    form = await _parse_form(request)
    file = form.get("file")
    if file is None or not _is_upload_file(file):
        raise BadRequestError("请上传文件", details={"field": "file"})
    subpath = form.get("subpath")
    subpath_str = (subpath if isinstance(subpath, str) else (subpath or "")) or ""
    input_dir, _, _ = get_workspace_dirs(workspace_id)
    content = await file.read()
    path, err = save_upload_to_dir(
        input_dir,
        content,
        file.filename or "file",
        subpath_str.strip(),
        ALLOWED_EXT,
        "input/",
    )
    if err:
        return {"error": err}
    return {"path": path, "saved": True}
