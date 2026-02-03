# -*- coding: utf-8 -*-
"""
input 文件夹：列出文件、上传并保存到 input。
"""
import os
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form
from typing import Optional

router = APIRouter()

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_INPUT_DIR = os.path.join(_ROOT, "input")

# 允许的剧本扩展名
ALLOWED_EXT = {".md", ".docx", ".pdf"}


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
def list_input_files():
    """列出 input 目录下所有文件（递归），返回相对 input 的路径。仅包含 .md/.docx/.pdf。"""
    if not os.path.isdir(_INPUT_DIR):
        return {"files": []}
    out = []
    for root, _, names in os.walk(_INPUT_DIR):
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext not in ALLOWED_EXT:
                continue
            full = os.path.join(root, name)
            rel = _safe_relative(full, _INPUT_DIR)
            if rel:
                # 返回相对项目根的路径，供 analyze-path 使用
                out.append({"path": "input/" + rel, "name": name})
    out.sort(key=lambda x: x["path"])
    return {"files": out}


@router.post("/upload")
async def upload_to_input(
    file: UploadFile = File(...),
    subpath: Optional[str] = Form(""),
):
    """
    上传文件并保存到 input 目录。subpath 为相对 input 的子目录，如 "郑州轻工业大学《编译原理》"。
    返回保存后的相对项目根路径，如 input/xxx.md。
    """
    name = (file.filename or "file").strip()
    if not name:
        name = "file"
    # 防止路径穿越
    name = os.path.basename(name)
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXT:
        return {"error": f"仅支持 {', '.join(ALLOWED_EXT)} 格式"}
    subpath = (subpath or "").strip().replace("\\", "/").strip("/")
    target_dir = os.path.join(_INPUT_DIR, subpath) if subpath else _INPUT_DIR
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, name)
    content = await file.read()
    with open(target_path, "wb") as f:
        f.write(content)
    rel_to_root = _safe_relative(target_path, _ROOT) or f"input/{name}"
    return {"path": rel_to_root.replace("\\", "/"), "saved": True}
