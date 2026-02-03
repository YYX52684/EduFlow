# -*- coding: utf-8 -*-
import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from parsers import parse_markdown, parse_docx, parse_pdf
from generators import ContentSplitter

router = APIRouter()

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _get_parser_for_ext(ext: str):
    ext = (ext or "").lower()
    parsers = {".md": parse_markdown, ".docx": parse_docx, ".pdf": parse_pdf}
    if ext not in parsers:
        raise ValueError(f"不支持的文件格式: {ext}。支持: {', '.join(parsers.keys())}")
    return parsers[ext]


@router.post("/upload")
async def upload_and_analyze(file: UploadFile = File(...)):
    """上传剧本文件，解析内容并分析结构。返回 full_content 与 stages。"""
    suffix = os.path.splitext(file.filename or "")[1].lower()
    if not suffix:
        suffix = ".md"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        path = tmp.name
    try:
        parser = _get_parser_for_ext(suffix)
        full_content = parser(path)
        splitter = ContentSplitter()
        result = splitter.analyze(full_content)
        stages = result.get("stages", [])
        return {
            "filename": file.filename,
            "full_content_length": len(full_content),
            "stages_count": len(stages),
            "stages": [
                {
                    "id": s.get("id"),
                    "title": s.get("title"),
                    "description": s.get("description"),
                    "role": s.get("role"),
                    "task": s.get("task"),
                    "key_points": s.get("key_points", []),
                    "content_excerpt": s.get("content_excerpt") or "",
                }
                for s in stages
            ],
            "full_content": full_content,
        }
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


class AnalyzePathRequest(BaseModel):
    path: str  # 相对项目根，如 input/示例剧本.md


@router.post("/analyze-path")
def analyze_by_path(req: AnalyzePathRequest):
    """根据项目内文件路径解析并分析结构（用于选择 input 中已有文件）。"""
    path = req.path.strip().replace("\\", "/")
    if path.startswith("/") or ".." in path:
        raise HTTPException(status_code=400, detail="路径不合法")
    full = os.path.join(_ROOT, path)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail=f"文件不存在: {req.path}")
    suffix = os.path.splitext(full)[1].lower()
    if suffix not in (".md", ".docx", ".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 .md / .docx / .pdf")
    try:
        parser = _get_parser_for_ext(suffix)
        full_content = parser(full)
        splitter = ContentSplitter()
        result = splitter.analyze(full_content)
        stages = result.get("stages", [])
        return {
            "filename": os.path.basename(full),
            "path": path,
            "full_content_length": len(full_content),
            "stages_count": len(stages),
            "stages": [
                {
                    "id": s.get("id"),
                    "title": s.get("title"),
                    "description": s.get("description"),
                    "role": s.get("role"),
                    "task": s.get("task"),
                    "key_points": s.get("key_points", []),
                    "content_excerpt": s.get("content_excerpt") or "",
                }
                for s in stages
            ],
            "full_content": full_content,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
