# -*- coding: utf-8 -*-
"""
output 目录：列出当前工作区 output 下的文件、上传外部评估报告等。
支持读取/写入文件内容，供卡片可视化编辑使用。
"""
import os
from urllib.parse import quote
from fastapi import APIRouter, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from api.routes.auth import require_workspace_owned
from api.workspace import get_project_dirs, resolve_workspace_path, normalize_output_rel, list_dir_files, list_dir_files_with_mtime, save_upload_to_dir
from api.exceptions import NotFoundError, LLMError

# 评估报告允许的扩展名
EXPORT_ALLOWED_EXT = {".md", ".json", ".txt"}


class WriteBody(BaseModel):
    path: str  # 相对 output，如 output/cards_xxx.md 或 cards_xxx.md
    content: str


@router.get("/read")
def read_output_file(
    path: str,
    workspace_id: str = Depends(require_workspace_owned),
):
    """读取 output 下指定文件的文本内容，用于卡片编辑。path 如 output/cards_xxx.md。"""
    full_path = resolve_workspace_path(workspace_id, path, kind="output", must_exist=True)
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise LLMError("读取失败", details={"path": path, "reason": str(e)})
    return {"path": normalize_output_rel(path), "content": content}


@router.get("/download")
def download_output_file(
    path: str,
    workspace_id: str = Depends(require_workspace_owned),
):
    """下载 output 下指定文件（不选本地目录也可用）。path 如 output/cards_xxx.md。"""
    full_path = resolve_workspace_path(workspace_id, path, kind="output", must_exist=True)
    filename = os.path.basename(full_path)
    return FileResponse(
        full_path,
        filename=filename,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/write")
def write_output_file(
    body: WriteBody,
    workspace_id: str = Depends(require_workspace_owned),
):
    """将文本内容写入 output 下指定路径，用于保存编辑后的卡片。路径不存在则创建。"""
    full_path = resolve_workspace_path(workspace_id, body.path, kind="output")
    try:
        os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(body.content)
    except Exception as e:
        raise LLMError("写入失败", details={"path": body.path, "reason": str(e)})
    return {"path": normalize_output_rel(body.path), "saved": True}


@router.get("/files")
def list_output_files(
    with_mtime: bool = False,
    workspace_id: str = Depends(require_workspace_owned),
):
    """列出当前工作区 output 目录下所有文件（递归）。with_mtime=1 时每条带 mtime 时间戳（秒）便于按时间排序。"""
    _, output_dir, _ = get_project_dirs(workspace_id)
    if with_mtime:
        files = list_dir_files_with_mtime(output_dir, "output/", allowed_ext=None)
    else:
        files = list_dir_files(output_dir, "output/", allowed_ext=None)
    return {"files": files}


@router.post("/upload")
async def upload_to_output(
    workspace_id: str = Depends(require_workspace_owned),
    file: UploadFile = File(...),
    subpath: Optional[str] = Form("output/optimizer"),
    save_as: Optional[str] = Form(""),
):
    """
    上传文件到当前工作区 output。用于上传外部评估报告等。
    subpath: 相对 output 的子路径，默认 output/optimizer。
    save_as: 保存为的文件名，空则用原文件名；可填 export_score.md 以覆盖默认导出路径。
    """
    _, output_dir, _ = get_project_dirs(workspace_id)
    content = await file.read()
    subpath_str = (subpath or "output/optimizer").strip().replace("\\", "/").strip("/")
    path, err = save_upload_to_dir(
        output_dir,
        content,
        file.filename or "file",
        subpath_str,
        EXPORT_ALLOWED_EXT,
        "output/",
        save_as=save_as,
    )
    if err:
        return {"error": err}
    return {"path": path, "saved": True}
