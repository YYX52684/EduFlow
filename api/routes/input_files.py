# -*- coding: utf-8 -*-
"""
input 文件夹：按工作区列出文件、上传并保存到该工作区 input。
"""
import os
from fastapi import APIRouter, UploadFile, File, Form, Depends
from typing import Optional

router = APIRouter()

from api.workspace import get_workspace_id, get_workspace_dirs

# 允许的剧本扩展名
ALLOWED_EXT = {".md", ".docx", ".doc", ".pdf"}


def _safe_relative(path: str, base: str) -> Optional[str]:
    """返回 path 相对 base 的路径，若不在 base 下则返回 None。"""
    try:
        r = os.path.relpath(path, base)
        if r.startswith("..") or os.path.isabs(r):
            return None
        return r.replace("\\", "/")
    except Exception:
        return None


@router.get("/files")
def list_input_files(workspace_id: str = Depends(get_workspace_id)):
    """列出当前工作区 input 目录下所有文件（递归）。"""
    input_dir, _, _ = get_workspace_dirs(workspace_id)
    if not os.path.isdir(input_dir):
        return {"files": []}
    out = []
    for root, _, names in os.walk(input_dir):
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext not in ALLOWED_EXT:
                continue
            full = os.path.join(root, name)
            rel = _safe_relative(full, input_dir)
            if rel:
                out.append({"path": "input/" + rel, "name": name})
    out.sort(key=lambda x: x["path"])
    return {"files": out}


@router.post("/upload")
async def upload_to_input(
    workspace_id: str = Depends(get_workspace_id),
    file: UploadFile = File(...),
    subpath: Optional[str] = Form(""),
):
    """上传文件并保存到当前工作区 input。返回相对路径如 input/xxx.md。"""
    input_dir, _, _ = get_workspace_dirs(workspace_id)
    name = (file.filename or "file").strip() or "file"
    name = os.path.basename(name)
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXT:
        return {"error": f"仅支持 {', '.join(ALLOWED_EXT)} 格式"}
    subpath = (subpath or "").strip().replace("\\", "/").strip("/")
    target_dir = os.path.join(input_dir, subpath) if subpath else input_dir
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, name)
    content = await file.read()
    with open(target_path, "wb") as f:
        f.write(content)
    rel = _safe_relative(target_path, input_dir) or name
    return {"path": "input/" + rel.replace("\\", "/"), "saved": True}
