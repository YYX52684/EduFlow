# -*- coding: utf-8 -*-
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

router = APIRouter()

from config import OUTPUT_DIR, DEEPSEEK_API_KEY, CARD_GENERATOR_TYPE, EVALUATION_CONFIG
from generators import list_frameworks, get_framework
from generators.evaluation_section import build_evaluation_markdown


class GenerateRequest(BaseModel):
    full_content: str
    stages: List[Dict[str, Any]]
    framework_id: Optional[str] = None
    source_filename: Optional[str] = None


def _progress_callback(current: int, total: int, message: str):
    pass


@router.post("/generate")
def generate_cards(req: GenerateRequest):
    """根据已分析的剧本内容生成教学卡片。"""
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="未配置 DEEPSEEK_API_KEY")
    stages = req.stages
    if not stages:
        raise HTTPException(status_code=400, detail="stages 不能为空")
    framework_id = req.framework_id or CARD_GENERATOR_TYPE
    frameworks = list_frameworks()
    if not frameworks:
        raise HTTPException(status_code=500, detail="无可用生成框架")
    if framework_id and not any(m["id"] == framework_id for m in frameworks):
        framework_id = frameworks[0]["id"]
    if not framework_id:
        framework_id = frameworks[0]["id"]
    try:
        GeneratorClass, meta = get_framework(framework_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        generator = GeneratorClass(api_key=DEEPSEEK_API_KEY)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"初始化生成器失败: {e}")
    cards_content = generator.generate_all_cards(
        stages,
        req.full_content,
        progress_callback=_progress_callback,
    )
    task_meta = {
        "task_name": req.source_filename or "未命名",
        "description": "",
        "evaluation_items": [],
    }
    if EVALUATION_CONFIG.get("enabled", True):
        evaluation_md = build_evaluation_markdown(
            task_meta.get("evaluation_items", []),
            stages,
            target_total_score=EVALUATION_CONFIG.get("target_total_score", 100),
            auto_generate_if_empty=EVALUATION_CONFIG.get("auto_generate", True),
        )
        if evaluation_md:
            cards_content = cards_content + "\n\n---\n\n" + evaluation_md
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"cards_output_{timestamp}.md"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    header = f"""# 教学卡片

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 源文件: {req.source_filename or 'API'}
> 阶段数量: {len(stages)}

---

"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + cards_content)
    return {
        "output_path": output_path,
        "output_filename": output_filename,
        "stages_count": len(stages),
        "cards_count": len(stages) * 2,
        "content_preview": (header + cards_content)[:2000],
    }
