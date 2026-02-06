# -*- coding: utf-8 -*-
"""
工作区 LLM 配置：单一 API Key + 模型选择，全系统共用。
存于 workspaces/<id>/llm_config.json，未设置时回退到 .env。
"""
import os
import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from api.workspace import get_workspace_id, get_workspace_dirs

LLM_CONFIG_FILE = "llm_config.json"

# 预设：model_type -> (base_url, model_name)
PRESETS = {
    "deepseek": ("https://api.deepseek.com", "deepseek-chat"),
    "doubao": ("http://llm-service.polymas.com/api/openai/v1", "Doubao-1.5-pro-32k"),
    "openai": ("https://api.openai.com/v1", "gpt-4o"),
}


def _config_path(workspace_id: str) -> str:
    _, _, root = get_workspace_dirs(workspace_id)
    return os.path.join(root, LLM_CONFIG_FILE)


def get_llm_config(workspace_id: Optional[str] = None) -> dict:
    """
    获取当前生效的 LLM 配置（API Key + base_url + model）。
    若提供 workspace_id 且该工作区有 llm_config.json，则使用；否则从 .env 读取。
    返回: {"api_key": str, "model_type": str, "base_url": str, "model": str}
    """
    from dotenv import load_dotenv
    load_dotenv()
    env_key_ds = os.getenv("DEEPSEEK_API_KEY")
    env_key_db = os.getenv("LLM_API_KEY")
    env_model_type = (os.getenv("MODEL_TYPE") or "deepseek").lower()

    cfg = {}
    if workspace_id:
        path = _config_path(workspace_id)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                pass

    model_type = (cfg.get("model_type") or env_model_type or "deepseek").strip().lower()
    if model_type not in PRESETS:
        model_type = "deepseek"
    base_url = (cfg.get("base_url") or "").strip() or PRESETS[model_type][0]
    model_name = (cfg.get("model") or "").strip() or PRESETS[model_type][1]
    api_key = (cfg.get("api_key") or "").strip()
    if not api_key:
        api_key = (env_key_db if model_type == "doubao" else env_key_ds) or ""

    return {
        "api_key": api_key,
        "model_type": model_type,
        "base_url": base_url.rstrip("/"),
        "model": model_name,
    }


@router.get("/config")
def get_config(workspace_id: str = Depends(get_workspace_id)):
    """返回当前工作区 LLM 配置（用于设置页展示）。api_key 脱敏返回。"""
    path = _config_path(workspace_id)
    raw = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            pass
    # 未保存时从 env 补全展示
    from dotenv import load_dotenv
    load_dotenv()
    model_type = (raw.get("model_type") or os.getenv("MODEL_TYPE") or "deepseek").strip().lower()
    if model_type not in PRESETS:
        model_type = "deepseek"
    base_url = (raw.get("base_url") or "").strip() or PRESETS[model_type][0]
    model = (raw.get("model") or "").strip() or PRESETS[model_type][1]
    api_key = (raw.get("api_key") or "").strip()
    mask = (api_key[:8] + "…" + api_key[-4:]) if len(api_key) > 12 else ("已设置" if api_key else "")
    return {
        "model_type": model_type,
        "base_url": base_url,
        "model": model,
        "api_key_masked": mask,
        "has_api_key": bool(api_key),
    }


class LLMConfigUpdate(BaseModel):
    api_key: Optional[str] = None
    model_type: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


@router.post("/config")
def save_config(body: LLMConfigUpdate, workspace_id: str = Depends(get_workspace_id)):
    """保存当前工作区 LLM 配置（API Key + 模型）。全系统解析、生成卡片、优化器、模拟器均使用此配置。"""
    path = _config_path(workspace_id)
    current = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                current = json.load(f)
        except Exception:
            pass
    if body.api_key is not None:
        current["api_key"] = (body.api_key or "").strip()
    if body.model_type is not None:
        t = (body.model_type or "deepseek").strip().lower()
        current["model_type"] = t if t in PRESETS else "deepseek"
    if body.base_url is not None:
        current["base_url"] = (body.base_url or "").strip()
    if body.model is not None:
        current["model"] = (body.model or "").strip()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    return {"message": "已保存，本工作区将使用该 API Key 与模型"}


@router.get("/presets")
def list_presets():
    """返回可选模型预设（用于前端下拉）。"""
    return {
        "presets": [
            {"id": "deepseek", "name": "DeepSeek", "base_url": PRESETS["deepseek"][0], "model": PRESETS["deepseek"][1]},
            {"id": "doubao", "name": "豆包", "base_url": PRESETS["doubao"][0], "model": PRESETS["doubao"][1]},
            {"id": "openai", "name": "OpenAI 兼容（自定义）", "base_url": PRESETS["openai"][0], "model": PRESETS["openai"][1]},
        ]
    }
