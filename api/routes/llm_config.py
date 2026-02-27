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

from api.routes.auth import require_workspace_owned
from api.workspace import get_workspace_file_path

LLM_CONFIG_FILE = "llm_config.json"

# 预设：model_type -> (base_url, model_name)
PRESETS = {
    "deepseek": ("https://api.deepseek.com", "deepseek-chat"),
    "doubao": ("https://llm-service.polymas.com/api/openai/v1", "Doubao-1.5-pro-32k"),
    "openai": ("https://api.openai.com/v1", "gpt-4o"),
}


def build_chat_completions_url(base_url: str) -> str:
    """
    根据基础 base_url 构建 OpenAI Chat Completions 端点。

    约定：
    - 若 base_url 以 /v1 结尾（如 https://api.openai.com/v1 或 .../api/openai/v1），拼接 /chat/completions；
    - 否则在末尾补 /v1/chat/completions（如 https://api.deepseek.com → https://api.deepseek.com/v1/chat/completions）。
    """
    base = (base_url or "").rstrip("/")
    if not base:
        return ""
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _config_path(workspace_id: str) -> str:
    return get_workspace_file_path(workspace_id, LLM_CONFIG_FILE)


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
    # 默认优先使用豆包（公司内网 LLM），除非显式指定 MODEL_TYPE=deepseek
    env_model_type = (os.getenv("MODEL_TYPE") or "doubao").lower()

    cfg = {}
    if workspace_id:
        path = _config_path(workspace_id)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                pass

    model_type = (cfg.get("model_type") or env_model_type or "doubao").strip().lower()
    if model_type not in PRESETS:
        model_type = "doubao"
    base_url = (cfg.get("base_url") or "").strip() or PRESETS[model_type][0]
    model_name = (cfg.get("model") or "").strip() or PRESETS[model_type][1]
    api_key = (cfg.get("api_key") or "").strip()
    if not api_key:
        api_key = (env_key_db if model_type == "doubao" else env_key_ds) or ""
    # 用户未设置时，使用 .env 中已有的豆包 Key（LLM_API_KEY）作为默认，不向用户暴露
    if not api_key and env_key_db:
        api_key = (env_key_db or "").strip()
        if api_key:
            model_type = "doubao"
            base_url = PRESETS["doubao"][0]
            model_name = PRESETS["doubao"][1]

    return {
        "api_key": api_key,
        "model_type": model_type,
        "base_url": base_url.rstrip("/"),
        "model": model_name,
    }


def require_llm_config(workspace_id: Optional[str] = None) -> dict:
    """
    获取 LLM 配置，若未配置完整（api_key / base_url / model 任一缺失）则抛出 ConfigError。
    用于需要强依赖 LLM 的接口（生成卡片、仿真、评估、优化器等）。
    """
    from api.exceptions import ConfigError

    llm = get_llm_config(workspace_id)
    api_key = (llm.get("api_key") or "").strip()
    base_url = (llm.get("base_url") or "").rstrip("/")
    model = (llm.get("model") or "").strip()
    if not api_key or not base_url or not model:
        raise ConfigError("未配置完整的 LLM 信息，请在「设置」中填写 API Key 与模型。")
    return llm


@router.get("/config")
def get_config(workspace_id: str = Depends(require_workspace_owned)):
    """返回当前工作区 LLM 配置（用于设置页展示）。api_key 脱敏返回，默认免费 Key 不暴露。"""
    path = _config_path(workspace_id)
    raw = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            pass
    raw_key = (raw.get("api_key") or "").strip()
    llm = get_llm_config(workspace_id)
    model_type = (llm.get("model_type") or "doubao").strip().lower()
    base_url = (llm.get("base_url") or "").rstrip("/") or PRESETS.get(model_type, PRESETS["doubao"])[0]
    model = (llm.get("model") or "").strip() or PRESETS.get(model_type, PRESETS["doubao"])[1]
    api_key = (llm.get("api_key") or "").strip()
    env_key_db = (os.getenv("LLM_API_KEY") or "").strip()
    using_default_free = bool(not raw_key and api_key and env_key_db and api_key == env_key_db)
    if using_default_free:
        mask = "默认体验（豆包）"
    elif api_key:
        mask = (api_key[:8] + "…" + api_key[-4:]) if len(api_key) > 12 else "已设置"
    else:
        mask = ""
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
def save_config(body: LLMConfigUpdate, workspace_id: str = Depends(require_workspace_owned)):
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
        t = (body.model_type or "doubao").strip().lower()
        current["model_type"] = t if t in PRESETS else "doubao"
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
