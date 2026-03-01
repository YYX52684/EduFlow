# -*- coding: utf-8 -*-
"""
input 文件夹：按工作区列出文件、上传并保存到该工作区 input。
"""
from fastapi import APIRouter, Request, UploadFile, Depends
from typing import Optional

router = APIRouter()

from api.routes.auth import require_workspace_owned
from api.workspace import get_workspace_dirs, list_dir_files, save_upload_to_dir
from api.exceptions import BadRequestError

# 允许的剧本扩展名
ALLOWED_EXT = {".md", ".docx", ".doc", ".pdf"}

# 放宽 multipart 单 part 大小，避免大文件触发 413/400
MAX_UPLOAD_PART_SIZE = 50 * 1024 * 1024  # 50MB


async def _parse_form(request: Request):
    try:
        return await request.form(max_part_size=MAX_UPLOAD_PART_SIZE)
    except TypeError:
        return await request.form()


@router.get("/files")
def list_input_files(workspace_id: str = Depends(require_workspace_owned)):
    """列出当前工作区 input 目录下所有文件（递归）。"""
    input_dir, _, _ = get_workspace_dirs(workspace_id)
    files = list_dir_files(input_dir, "input/", allowed_ext=ALLOWED_EXT)
    return {"files": files}


@router.post("/upload")
async def upload_to_input(
    request: Request,
    workspace_id: str = Depends(require_workspace_owned),
):
    """上传文件并保存到当前工作区 input。返回相对路径如 input/xxx.md。单文件最大约 50MB。"""
    form = await _parse_form(request)
    file = form.get("file")
    if file is None or not isinstance(file, UploadFile):
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
