# -*- coding: utf-8 -*-
import asyncio
import json
import os
import queue
import re
import threading
from datetime import datetime
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

router = APIRouter()

from config import CARD_GENERATOR_TYPE, EVALUATION_CONFIG
from api.routes.auth import require_workspace_owned
from api.workspace import get_project_dirs, get_workspace_dirs, resolve_workspace_path, safe_relative
from api.routes.llm_config import require_llm_config
from api.exceptions import BadRequestError, ConfigError, ValidationError
from generators import list_frameworks, get_framework
from generators.evaluation_section import build_evaluation_markdown

_FS_UNSAFE = re.compile(r'[\\/:*?"<>|\s]+')
_OUTPUT_WRITE_LOCK = threading.Lock()
_BATCH_MAX_CONCURRENCY_LIMIT = max(1, int(os.getenv("EDUFLOW_BATCH_MAX_CONCURRENCY", "4")))


class GenerateRequest(BaseModel):
    full_content: str
    stages: List[Dict[str, Any]]
    framework_id: Optional[str] = None
    source_filename: Optional[str] = None


class BatchGenerateRequest(BaseModel):
    items: List[GenerateRequest]
    max_concurrency: Optional[int] = None


def _sanitize_cards_basename(source_filename: Optional[str]) -> str:
    name = os.path.basename((source_filename or "").strip())
    name = os.path.splitext(name)[0].strip()
    name = _FS_UNSAFE.sub("_", name).strip("_")
    name = name[:80] if len(name) > 80 else name
    return name or "document"


def _normalize_batch_concurrency(requested: Optional[int], total: int) -> int:
    if total <= 0:
        return 1
    if requested is None:
        return min(total, _BATCH_MAX_CONCURRENCY_LIMIT)
    try:
        value = int(requested)
    except (TypeError, ValueError):
        value = 1
    return max(1, min(value, total, _BATCH_MAX_CONCURRENCY_LIMIT))


def _build_output_header(req: GenerateRequest, stages: List[Dict[str, Any]]) -> str:
    return f"""# 教学卡片

> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 源文件: {req.source_filename or 'API'}
> 阶段数量: {len(stages)}

---

"""


def _write_cards_output_file(
    workspace_id: str,
    source_filename: Optional[str],
    content: str,
) -> tuple[str, str, str]:
    _, project_output_dir, _ = get_project_dirs(workspace_id)
    _, workspace_output_dir, _ = get_workspace_dirs(workspace_id)
    base_name = _sanitize_cards_basename(source_filename)
    preferred = f"cards_{base_name}.md"
    with _OUTPUT_WRITE_LOCK:
        output_filename = preferred
        stem, ext = os.path.splitext(preferred)
        counter = 2
        output_path = os.path.join(project_output_dir, output_filename)
        while os.path.exists(output_path):
            output_filename = f"{stem}_{counter}{ext}"
            output_path = os.path.join(project_output_dir, output_filename)
            counter += 1
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
    rel_from_output = safe_relative(output_path, workspace_output_dir) or output_filename
    rel_path = 'output/' + rel_from_output.replace('\\', '/')
    full_rel_path = f"workspaces/{workspace_id}/{rel_path}"
    return output_filename, rel_path, full_rel_path


def _run_generate_cards(
    req: GenerateRequest,
    workspace_id: str,
    progress_callback: Optional[Any] = None,
    card_callback: Optional[Any] = None,
) -> dict:
    """核心逻辑：校验、选框架、生成卡片、写文件。返回 output_path, output_filename, full_path, workspace_id, stages_count, cards_count。"""
    cfg = require_llm_config(workspace_id)
    stages = req.stages
    if not stages:
        raise BadRequestError('stages 不能为空')
    framework_id = req.framework_id or CARD_GENERATOR_TYPE or 'dspy'
    frameworks = list_frameworks()
    if not frameworks:
        raise ConfigError('无可用生成框架')
    if framework_id and not any(m['id'] == framework_id for m in frameworks):
        framework_id = frameworks[0]['id']
    if not framework_id:
        framework_id = frameworks[0]['id']
    try:
        GeneratorClass, meta = get_framework(framework_id)
    except ValueError as e:
        raise ValidationError(str(e), details={'framework_id': framework_id})
    try:
        generator = GeneratorClass(
            api_key=cfg['api_key'],
            model_type=cfg.get('model_type'),
            base_url=cfg.get('base_url') or None,
            model=cfg.get('model') or None,
        )
    except Exception as e:
        raise ConfigError('初始化生成器失败', details={'reason': str(e)})

    kwargs = {'progress_callback': progress_callback}
    if card_callback is not None:
        kwargs['card_callback'] = card_callback
    cards_content = generator.generate_all_cards(stages, req.full_content, **kwargs)

    task_meta = {
        'task_name': req.source_filename or '未命名',
        'description': '',
        'evaluation_items': [],
    }
    if EVALUATION_CONFIG.get('enabled', True):
        evaluation_md = build_evaluation_markdown(
            task_meta.get('evaluation_items', []),
            stages,
            target_total_score=EVALUATION_CONFIG.get('target_total_score', 100),
            auto_generate_if_empty=EVALUATION_CONFIG.get('auto_generate', True),
        )
        if evaluation_md:
            cards_content = cards_content + "\n\n---\n\n" + evaluation_md

    header = _build_output_header(req, stages)
    output_filename, rel_path, full_rel_path = _write_cards_output_file(
        workspace_id,
        req.source_filename,
        header + cards_content,
    )
    return {
        'output_path': rel_path,
        'output_filename': output_filename,
        'full_path': full_rel_path,
        'workspace_id': workspace_id,
        'stages_count': len(stages),
        'cards_count': len(stages) * 2,
    }


@router.post('/generate')
def generate_cards(req: GenerateRequest, workspace_id: str = Depends(require_workspace_owned)):
    """根据已分析的剧本内容生成教学卡片，保存到当前工作区 output。使用工作区 LLM 配置（设置中的 API Key + 模型）。"""
    result = _run_generate_cards(req, workspace_id)
    full_path = resolve_workspace_path(workspace_id, result['output_path'], kind='output', must_exist=True)
    with open(full_path, 'r', encoding='utf-8') as f:
        result['content_preview'] = f.read()[:2000]
    return result


@router.post('/generate-batch')
async def generate_cards_batch(
    req: BatchGenerateRequest,
    workspace_id: str = Depends(require_workspace_owned),
):
    """批量并发生成教学卡片；每项独立返回成功或失败，互不阻塞。"""
    items = req.items or []
    if not items:
        raise BadRequestError('items 不能为空')
    max_concurrency = _normalize_batch_concurrency(req.max_concurrency, len(items))
    semaphore = asyncio.Semaphore(max_concurrency)

    async def run_one(index: int, item: GenerateRequest):
        async with semaphore:
            try:
                result = await asyncio.to_thread(_run_generate_cards, item, workspace_id)
                return {
                    'index': index,
                    'success': True,
                    'source_filename': item.source_filename or '',
                    **result,
                }
            except Exception as e:
                return {
                    'index': index,
                    'success': False,
                    'source_filename': item.source_filename or '',
                    'error': str(e),
                }

    results = await asyncio.gather(*[run_one(i, item) for i, item in enumerate(items)])
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


@router.post('/generate-stream')
async def generate_cards_stream(req: GenerateRequest, workspace_id: str = Depends(require_workspace_owned)):
    """流式生成卡片：通过 SSE 推送进度与每张卡片内容，前端可实时展示。"""
    q = queue.Queue()

    def run():
        try:
            def progress_cb(current: int, total: int, message: str):
                q.put(('progress', {'current': current, 'total': total, 'message': message}))

            def card_cb(label: str, content: str):
                q.put(('card', {'label': label, 'content': content}))

            result = _run_generate_cards(req, workspace_id, progress_callback=progress_cb, card_callback=card_cb)
            q.put(('done', result))
        except Exception as e:
            import traceback
            traceback.print_exc()
            q.put(('error', str(e)))

    th = threading.Thread(target=run, daemon=True)
    th.start()

    async def event_stream():
        yield f"event: progress\ndata: {json.dumps({'current': 0, 'total': max(1, len(req.stages) * 2), 'message': '正在准备生成…'}, ensure_ascii=False)}\n\n"
        while True:
            try:
                typ, payload = q.get(timeout=0.2)
            except queue.Empty:
                await asyncio.sleep(0.1)
                continue
            if typ == 'progress':
                data = json.dumps({
                    **payload,
                    'percent': int(100 * payload['current'] / max(1, payload['total'])),
                }, ensure_ascii=False)
                yield f"event: progress\ndata: {data}\n\n"
            elif typ == 'card':
                yield f"event: card\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            elif typ == 'done':
                yield f"event: done\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                break
            elif typ == 'error':
                yield f"event: error\ndata: {json.dumps({'detail': payload}, ensure_ascii=False)}\n\n"
                break

    return StreamingResponse(
        event_stream(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
