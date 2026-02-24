# -*- coding: utf-8 -*-
"""
input 文件夹：按工作区列出文件、上传并保存到该工作区 input。
"""
from fastapi import APIRouter, UploadFile, File, Form, Depends
from typing import Optional

router = APIRouter()

from api.routes.auth import require_workspace_owned
from api.workspace import get_workspace_dirs, list_dir_files, save_upload_to_dir

# 允许的剧本扩展名
ALLOWED_EXT = {".md", ".docx", ".doc", ".pdf"}


@router.get("/files")
def list_input_files(workspace_id: str = Depends(require_workspace_owned)):
    """列出当前工作区 input 目录下所有文件（递归）。"""
    input_dir, _, _ = get_workspace_dirs(workspace_id)
    files = list_dir_files(input_dir, "input/", allowed_ext=ALLOWED_EXT)
    return {"files": files}


@router.post("/upload")
async def upload_to_input(
    workspace_id: str = Depends(require_workspace_owned),
    file: UploadFile = File(...),
    subpath: Optional[str] = Form(""),
):
    """上传文件并保存到当前工作区 input。返回相对路径如 input/xxx.md。"""
    input_dir, _, _ = get_workspace_dirs(workspace_id)
    content = await file.read()
    path, err = save_upload_to_dir(
        input_dir,
        content,
        file.filename or "file",
        subpath or "",
        ALLOWED_EXT,
        "input/",
    )
    if err:
        return {"error": err}
    return {"path": path, "saved": True}
