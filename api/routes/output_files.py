# -*- coding: utf-8 -*-
"""
output 目录：列出当前工作区 output 下的文件、上传评估报告等优化相关文件。
支持读取/写入文件内容，供卡片与评估结果的可视化编辑使用。
"""
import os
from urllib.parse import quote
from fastapi import APIRouter, Request, UploadFile, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from api.routes.auth import require_workspace_owned
from api.workspace import get_project_dirs, resolve_workspace_path, normalize_output_rel, list_dir_files, list_dir_files_with_mtime, save_upload_to_dir
from api.exceptions import NotFoundError, LLMError, BadRequestError

# 评估报告允许的扩展名
EXPORT_ALLOWED_EXT = {".md", ".json", ".txt"}

# 放宽 multipart 单 part 大小，避免大文件触发 413/400
MAX_UPLOAD_PART_SIZE = 50 * 1024 * 1024  # 50MB


async def _parse_form(request: Request):
    try:
        return await request.form(max_part_size=MAX_UPLOAD_PART_SIZE)
    except TypeError:
        return await request.form()


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
    request: Request,
    workspace_id: str = Depends(require_workspace_owned),
):
    """
    上传文件到当前工作区 output。可用于上传闭环评估报告、日志等优化相关文件。
    单文件最大约 50MB。form 字段：file（必填）、subpath（默认 output/optimizer）、save_as（可选）。
    """
    form = await _parse_form(request)
    file = form.get("file")
    if file is None or not isinstance(file, UploadFile):
        raise BadRequestError("请上传文件", details={"field": "file"})
    subpath = form.get("subpath")
    subpath_str = (subpath if isinstance(subpath, str) else (subpath or "")) or "output/optimizer"
    save_as_raw = form.get("save_as")
    save_as = (save_as_raw if isinstance(save_as_raw, str) else (save_as_raw or "")) or ""
    _, output_dir, _ = get_project_dirs(workspace_id)
    content = await file.read()
    subpath_str = subpath_str.strip().replace("\\", "/").strip("/")
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


class DeleteOutputRequest(BaseModel):
    path: str  # 相对 output，如 output/xxx/file.json


@router.delete("/delete")
def delete_output_file(
    body: DeleteOutputRequest,
    workspace_id: str = Depends(require_workspace_owned),
):
    """删除 output 下指定文件；path 必须落在当前工作区 output 内。"""
    path = (body.path or "").strip().replace("\\", "/")
    if not path or ".." in path:
        raise BadRequestError("path 非法", details={"path": path})
    if not path.startswith("output/"):
        path = "output/" + path.lstrip("/")
    full_path = resolve_workspace_path(workspace_id, path, kind="output", must_exist=True)
    if not os.path.isfile(full_path):
        raise NotFoundError("文件不存在或非文件", details={"path": path})
    try:
        os.remove(full_path)
    except Exception as e:
        raise LLMError("删除失败", details={"path": path, "reason": str(e)})
    return {"deleted": path}
