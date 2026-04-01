# -*- coding: utf-8 -*-
import asyncio
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Depends, Request
from starlette.datastructures import UploadFile as StarletteUploadFile
from pydantic import BaseModel
from parsers import get_parser_for_extension
from generators import ContentSplitter
from generators.trainset_builder import write_trainset_for_document
from api.routes.auth import require_workspace_owned
from api.workspace import get_project_dirs, resolve_workspace_path
from api.routes.llm_config import get_llm_config, require_llm_config
from api.exceptions import BadRequestError, LLMError

router = APIRouter()

MAX_UPLOAD_PART_SIZE = 50 * 1024 * 1024  # 50MB
_BATCH_ANALYZE_MAX_CONCURRENCY_LIMIT = max(1, int(os.getenv('EDUFLOW_BATCH_ANALYZE_MAX_CONCURRENCY', '3')))


async def _parse_form(request: Request):
    try:
        return await request.form(max_part_size=MAX_UPLOAD_PART_SIZE)
    except TypeError:
        return await request.form()


def _is_upload_file(value: object) -> bool:
    return isinstance(value, (UploadFile, StarletteUploadFile))


def _normalize_batch_concurrency(requested: Optional[object], total: int) -> int:
    if total <= 0:
        return 1
    if requested in (None, ''):
        return min(total, _BATCH_ANALYZE_MAX_CONCURRENCY_LIMIT)
    try:
        value = int(requested)
    except (TypeError, ValueError):
        value = 1
    return max(1, min(value, total, _BATCH_ANALYZE_MAX_CONCURRENCY_LIMIT))


def _parse_file_to_content(path: str, suffix: str) -> str:
    """根据路径与扩展名解析文件，返回纯文本内容。"""
    parser = get_parser_for_extension(suffix)
    return parser(path)


def _stages_to_trainset_format(stages: list) -> list:
    """将 ContentSplitter 的 stages 转为 trainset 所需格式。保留 interaction_rounds 供卡片生成使用。"""
    return [
        {
            'id': s.get('id'),
            'title': s.get('title'),
            'description': s.get('description'),
            'role': s.get('role'),
            'task': s.get('task'),
            'key_points': s.get('key_points', []),
            'content_excerpt': s.get('content_excerpt') or '',
            'interaction_rounds': s.get('interaction_rounds'),
        }
        for s in stages
    ]


def _write_trainset_lib(
    workspace_id: str,
    full_content: str,
    stages_for_trainset: list,
    source_file: str,
) -> Optional[str]:
    """
    将当前文档写入工作区 trainset 库：output/trainset_lib/{原文档名}_trainset.json。
    任何异常不抛出，返回 None；成功返回相对路径（如 output/trainset_lib/xxx_trainset.json）。
    """
    if not workspace_id or not stages_for_trainset:
        return None
    try:
        _, output_dir, _ = get_project_dirs(workspace_id)
        return write_trainset_for_document(
            output_dir,
            source_file,
            full_content,
            stages_for_trainset,
            source_file=source_file,
        )
    except Exception:
        return None


def _build_splitter(workspace_id: str, require_config: bool = False) -> ContentSplitter:
    llm = require_llm_config(workspace_id) if require_config else (get_llm_config(workspace_id) if workspace_id else {})
    return ContentSplitter(
        api_key=llm.get('api_key') or None,
        base_url=llm.get('base_url') or None,
        model=llm.get('model') or None,
    )


def _build_analysis_response(
    workspace_id: str,
    source_file: str,
    full_content: str,
    analysis: dict,
    relative_path: Optional[str] = None,
) -> dict:
    stages = analysis.get('stages', [])
    stages_for_trainset = _stages_to_trainset_format(stages)
    out = {
        'filename': os.path.basename(source_file),
        'full_content_length': len(full_content),
        'stages_count': len(stages),
        'stages': stages_for_trainset,
        'full_content': full_content,
    }
    if relative_path:
        out['path'] = relative_path
    if analysis.get('_truncated_note'):
        out['truncated_note'] = analysis['_truncated_note']
    trainset_path = _write_trainset_lib(
        workspace_id,
        full_content,
        stages_for_trainset,
        os.path.basename(source_file),
    )
    if trainset_path is not None:
        out['trainset_path'] = trainset_path
        out['trainset_count'] = 1
    return out


def _analyze_content_sync(
    workspace_id: str,
    source_file: str,
    full_content: str,
    require_config: bool = False,
    relative_path: Optional[str] = None,
) -> dict:
    splitter = _build_splitter(workspace_id, require_config=require_config)
    result = splitter.analyze(full_content)
    return _build_analysis_response(
        workspace_id=workspace_id,
        source_file=source_file,
        full_content=full_content,
        analysis=result,
        relative_path=relative_path,
    )


def _analyze_path_sync(
    workspace_id: str,
    path: str,
    source_name: str,
    require_config: bool = False,
    relative_path: Optional[str] = None,
) -> dict:
    suffix = os.path.splitext(path)[1].lower() or '.md'
    full_content = _parse_file_to_content(path, suffix)
    return _analyze_content_sync(
        workspace_id=workspace_id,
        source_file=source_name,
        full_content=full_content,
        require_config=require_config,
        relative_path=relative_path,
    )


def _analyze_upload_bytes_sync(
    workspace_id: str,
    filename: str,
    content: bytes,
) -> dict:
    suffix = os.path.splitext(filename or '')[1].lower() or '.md'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        temp_path = tmp.name
    try:
        return _analyze_path_sync(
            workspace_id=workspace_id,
            path=temp_path,
            source_name=filename or 'file',
            require_config=False,
        )
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


@router.post('/upload')
async def upload_and_analyze(file: UploadFile = File(...), workspace_id: str = Depends(require_workspace_owned)):
    """上传剧本文件，解析内容并分析结构；需登录且写入当前用户工作区。"""
    try:
        content = await file.read()
        return await asyncio.to_thread(
            _analyze_upload_bytes_sync,
            workspace_id,
            file.filename or 'file',
            content,
        )
    except Exception as e:
        raise LLMError('上传解析或分析失败，' + str(e), details={'reason': str(e)})


@router.post('/upload-batch')
async def upload_and_analyze_batch(
    request: Request,
    workspace_id: str = Depends(require_workspace_owned),
):
    """批量上传多个剧本文件，逐项解析并分析结构；每项独立返回成功或失败。"""
    form = await _parse_form(request)
    files = []
    for field in ('files', 'file'):
        for item in form.getlist(field):
            if _is_upload_file(item):
                files.append(item)
    if not files:
        raise BadRequestError('请至少上传一个文件', details={'field': 'files'})

    max_concurrency = _normalize_batch_concurrency(form.get('max_concurrency'), len(files))
    payloads = []
    for upload in files:
        payloads.append({
            'filename': upload.filename or 'file',
            'content': await upload.read(),
        })

    semaphore = asyncio.Semaphore(max_concurrency)

    async def run_one(index: int, payload: dict):
        async with semaphore:
            try:
                data = await asyncio.to_thread(
                    _analyze_upload_bytes_sync,
                    workspace_id,
                    payload['filename'],
                    payload['content'],
                )
                return {
                    'index': index,
                    'success': True,
                    **data,
                }
            except Exception as e:
                return {
                    'index': index,
                    'success': False,
                    'filename': payload['filename'],
                    'error': str(e),
                }

    results = await asyncio.gather(*[run_one(i, payload) for i, payload in enumerate(payloads)])
    results.sort(key=lambda item: item.get('index', 0))
    success_count = sum(1 for item in results if item.get('success'))
    failure_count = len(results) - success_count
    return {
        'results': results,
        'total_count': len(results),
        'success_count': success_count,
        'failure_count': failure_count,
        'max_concurrency': max_concurrency,
    }


class AnalyzePathRequest(BaseModel):
    path: str  # 相对工作区，如 input/示例剧本.md


@router.post('/analyze-path')
def analyze_by_path(req: AnalyzePathRequest, workspace_id: str = Depends(require_workspace_owned)):
    """根据当前工作区 input 内文件路径解析并分析结构。"""
    path = req.path.strip().replace('\\', '/')
    if path.startswith('/') or '..' in path or not path.startswith('input/'):
        raise BadRequestError('路径不合法，应为 input/ 下路径', details={'path': path})
    full = resolve_workspace_path(workspace_id, path, kind='input', must_exist=True)
    try:
        return _analyze_path_sync(
            workspace_id=workspace_id,
            path=full,
            source_name=os.path.basename(full),
            require_config=True,
            relative_path=path,
        )
    except ValueError as e:
        raise BadRequestError(str(e), details={'path': req.path})
    except Exception as e:
        raise LLMError('按路径分析失败', details={'reason': str(e)})
