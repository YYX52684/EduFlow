# -*- coding: utf-8 -*-
import os
import tempfile
from fastapi import APIRouter, UploadFile, File, Depends, Header
from pydantic import BaseModel
from parsers import parse_markdown, parse_docx, parse_docx_with_structure, parse_doc_with_structure, parse_pdf
from generators import ContentSplitter
from generators.trainset_builder import append_trainset_example
from api.routes.auth import require_workspace_owned
from api.workspace import get_project_dirs, resolve_workspace_path
from api.routes.llm_config import get_llm_config, require_llm_config
from api.exceptions import BadRequestError, LLMError

router = APIRouter()


def _get_parser_for_ext(ext: str):
    ext = (ext or "").lower()
    parsers = {".md": parse_markdown, ".docx": parse_docx, ".doc": None, ".pdf": parse_pdf}
    if ext not in parsers:
        raise ValueError(f"不支持的文件格式: {ext}。支持: .md / .docx / .doc / .pdf")
    return parsers[ext]


@router.post("/upload")
async def upload_and_analyze(file: UploadFile = File(...), workspace_id: str = Depends(require_workspace_owned)):
    """上传剧本文件，解析内容并分析结构；需登录且写入当前用户工作区。"""
    suffix = os.path.splitext(file.filename or "")[1].lower()
    if not suffix:
        suffix = ".md"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        path = tmp.name
    try:
        if suffix == ".docx":
            full_content, _ = parse_docx_with_structure(path)
        elif suffix == ".doc":
            full_content, _ = parse_doc_with_structure(path)
        else:
            parser = _get_parser_for_ext(suffix)
            if parser is None:
                raise ValueError("不支持的文件格式")
            full_content = parser(path)
        llm = get_llm_config(workspace_id) if workspace_id else {}
        splitter = ContentSplitter(
            api_key=llm.get("api_key") or None,
            base_url=llm.get("base_url") or None,
            model=llm.get("model") or None,
        )
        result = splitter.analyze(full_content)
        stages = result.get("stages", [])
        stages_for_trainset = [
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
        ]
        out = {
            "filename": file.filename,
            "full_content_length": len(full_content),
            "stages_count": len(stages),
            "stages": stages_for_trainset,
            "full_content": full_content,
        }
        if result.get("_truncated_note"):
            out["truncated_note"] = result["_truncated_note"]
        if workspace_id and stages_for_trainset:
            try:
                _, output_dir, _ = get_project_dirs(workspace_id)
                trainset_path = os.path.join(output_dir, "optimizer", "trainset.json")
                count = append_trainset_example(
                    full_content, stages_for_trainset, trainset_path,
                    source_file=file.filename or "",
                )
                out["trainset_path"] = "output/optimizer/trainset.json"
                out["trainset_count"] = count
            except Exception:
                pass
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
    if suffix not in (".md", ".docx", ".doc", ".pdf"):
        raise BadRequestError("仅支持 .md / .docx / .doc / .pdf", details={"path": req.path})
    try:
        if suffix == ".docx":
            full_content, _ = parse_docx_with_structure(full)
        elif suffix == ".doc":
            full_content, _ = parse_doc_with_structure(full)
        else:
            parser = _get_parser_for_ext(suffix)
            if parser is None:
                raise BadRequestError("不支持的文件格式", details={"suffix": suffix})
            full_content = parser(full)
        llm = require_llm_config(workspace_id)
        splitter = ContentSplitter(
            api_key=llm.get("api_key") or None,
            base_url=llm.get("base_url") or None,
            model=llm.get("model") or None,
        )
        result = splitter.analyze(full_content)
        stages = result.get("stages", [])
        stages_for_trainset = [
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
        ]
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
        if stages_for_trainset:
            _, output_dir, _ = get_project_dirs(workspace_id)
            trainset_path = os.path.join(output_dir, "optimizer", "trainset.json")
            count = append_trainset_example(
                full_content, stages_for_trainset, trainset_path,
                source_file=full,
            )
            out["trainset_path"] = "output/optimizer/trainset.json"
            out["trainset_count"] = count
        return out
    except Exception as e:
        raise LLMError("按路径分析失败", details={"reason": str(e)})
