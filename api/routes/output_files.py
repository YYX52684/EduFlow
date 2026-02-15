# -*- coding: utf-8 -*-
"""
output 目录：列出当前工作区 output 下的文件、上传外部评估报告等。
支持读取/写入文件内容，供卡片可视化编辑使用。
"""
import os
from fastapi import APIRouter, UploadFile, File, Form, Depends
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from api.workspace import get_workspace_id, get_project_dirs, resolve_workspace_path
from api.exceptions import NotFoundError, LLMError

# 评估报告允许的扩展名
EXPORT_ALLOWED_EXT = {".md", ".json", ".txt"}


def _safe_relative(path: str, base: str) -> Optional[str]:
    try:
        r = os.path.relpath(path, base)
        if r.startswith("..") or os.path.isabs(r):
            return None
        return r.replace("\\", "/")
    except Exception:
        return None


class WriteBody(BaseModel):
    path: str  # 相对 output，如 output/cards_xxx.md 或 cards_xxx.md
    content: str


@router.get("/read")
def read_output_file(
    path: str,
    workspace_id: str = Depends(get_workspace_id),
):
    """读取 output 下指定文件的文本内容，用于卡片编辑。path 如 output/cards_xxx.md。"""
    full_path = resolve_workspace_path(workspace_id, path, kind="output", must_exist=True)
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise LLMError("读取失败", details={"path": path, "reason": str(e)})
    rel = path.strip().replace("\\", "/").lstrip("/")
    if not rel.startswith("output/"):
        rel = "output/" + rel
    return {"path": rel, "content": content}


@router.post("/write")
def write_output_file(
    body: WriteBody,
    workspace_id: str = Depends(get_workspace_id),
):
    """将文本内容写入 output 下指定路径，用于保存编辑后的卡片。路径不存在则创建。"""
    full_path = resolve_workspace_path(workspace_id, body.path, kind="output")
    try:
        os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(body.content)
    except Exception as e:
        raise LLMError("写入失败", details={"path": body.path, "reason": str(e)})
    rel = body.path.strip().replace("\\", "/").lstrip("/")
    if not rel.startswith("output/"):
        rel = "output/" + rel
    return {"path": rel, "saved": True}


@router.get("/files")
def list_output_files(workspace_id: str = Depends(get_workspace_id)):
    """列出当前工作区 output 目录下所有文件（递归）。"""
    _, output_dir, _ = get_project_dirs(workspace_id)
    if not os.path.isdir(output_dir):
        return {"files": []}
    out = []
    for root, _, names in os.walk(output_dir):
        for name in sorted(names):
            full = os.path.join(root, name)
            rel = _safe_relative(full, output_dir)
            if rel:
                out.append({"path": "output/" + rel, "name": name})
    out.sort(key=lambda x: x["path"])
    return {"files": out}


@router.post("/upload")
async def upload_to_output(
    workspace_id: str = Depends(get_workspace_id),
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
    name = (file.filename or "file").strip() or "file"
    name = os.path.basename(name)
    ext = os.path.splitext(name)[1].lower()
    if ext not in EXPORT_ALLOWED_EXT:
        return {"error": f"仅支持 {', '.join(EXPORT_ALLOWED_EXT)} 格式"}
    subpath = (subpath or "output/optimizer").strip().replace("\\", "/").strip("/")
    if subpath.startswith("output/"):
        subpath = subpath[7:]
    if save_as and save_as.strip():
        name = os.path.basename(save_as.strip())
    target_dir = os.path.join(output_dir, subpath)
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, name)
    content = await file.read()
    with open(target_path, "wb") as f:
        f.write(content)
    rel = "output/" + (os.path.join(subpath, name) if subpath else name).replace("\\", "/")
    return {"path": rel, "saved": True}
