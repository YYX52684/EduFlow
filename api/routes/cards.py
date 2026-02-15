# -*- coding: utf-8 -*-
import os
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

router = APIRouter()

from config import CARD_GENERATOR_TYPE, EVALUATION_CONFIG
from api.workspace import get_workspace_id, get_workspace_dirs
from api.routes.llm_config import require_llm_config
from api.exceptions import BadRequestError, ConfigError, ValidationError
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
def generate_cards(req: GenerateRequest, workspace_id: str = Depends(get_workspace_id)):
    """根据已分析的剧本内容生成教学卡片，保存到当前工作区 output。使用工作区 LLM 配置（设置中的 API Key + 模型）。"""
    cfg = require_llm_config(workspace_id)
    stages = req.stages
    if not stages:
        raise BadRequestError("stages 不能为空")
    framework_id = req.framework_id or CARD_GENERATOR_TYPE
    frameworks = list_frameworks()
    if not frameworks:
        raise ConfigError("无可用生成框架")
    if framework_id and not any(m["id"] == framework_id for m in frameworks):
        framework_id = frameworks[0]["id"]
    if not framework_id:
        framework_id = frameworks[0]["id"]
    try:
        GeneratorClass, meta = get_framework(framework_id)
    except ValueError as e:
        raise ValidationError(str(e), details={"framework_id": framework_id})
    try:
        if framework_id == "dspy":
            generator = GeneratorClass(
                api_key=cfg["api_key"],
                model_type=cfg.get("model_type"),
                base_url=cfg.get("base_url") or None,
                model=cfg.get("model") or None,
            )
        else:
            generator = GeneratorClass(
                api_key=cfg["api_key"],
                base_url=cfg.get("base_url") or None,
                model=cfg.get("model") or None,
            )
    except Exception as e:
        raise ConfigError("初始化生成器失败", details={"reason": str(e)})
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
    _, output_dir, _ = get_workspace_dirs(workspace_id)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"cards_output_{timestamp}.md"
    output_path = os.path.join(output_dir, output_filename)
    header = f"""# 教学卡片

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 源文件: {req.source_filename or 'API'}
> 阶段数量: {len(stages)}

---

"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + cards_content)
    rel_path = "output/" + output_filename
    # 便于用户定位：返回相对项目根的完整路径（workspaces/<id>/output/xxx.md）
    full_rel_path = f"workspaces/{workspace_id}/output/{output_filename}"
    return {
        "output_path": rel_path,
        "output_filename": output_filename,
        "full_path": full_rel_path,
        "workspace_id": workspace_id,
        "stages_count": len(stages),
        "cards_count": len(stages) * 2,
        "content_preview": (header + cards_content)[:2000],
    }
