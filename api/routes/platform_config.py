# -*- coding: utf-8 -*-
"""
智慧树平台配置的读取与保存（写入 .env，供注入使用）。
"""
import os
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

# 与 config.py 中 PLATFORM_CONFIG 对应的 .env 键名
PLATFORM_ENV_KEYS = [
    "PLATFORM_BASE_URL",
    "PLATFORM_COOKIE",
    "PLATFORM_AUTHORIZATION",
    "PLATFORM_COURSE_ID",
    "PLATFORM_TRAIN_TASK_ID",
    "PLATFORM_START_NODE_ID",
    "PLATFORM_END_NODE_ID",
]

# 默认值（与 config 一致）
DEFAULTS = {
    "PLATFORM_BASE_URL": "https://cloudapi.polymas.com",
}


def _env_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, ".env")


def _config_to_env_keys() -> dict:
    """当前 config 中 PLATFORM_* 对应的键名（用于 GET 返回的 key 与前端一致）"""
    return {
        "base_url": "PLATFORM_BASE_URL",
        "cookie": "PLATFORM_COOKIE",
        "authorization": "PLATFORM_AUTHORIZATION",
        "course_id": "PLATFORM_COURSE_ID",
        "train_task_id": "PLATFORM_TRAIN_TASK_ID",
        "start_node_id": "PLATFORM_START_NODE_ID",
        "end_node_id": "PLATFORM_END_NODE_ID",
    }


@router.get("/config")
def get_platform_config():
    """返回当前智慧树平台配置（供前端输入框回显）。"""
    import config
    cfg = config.PLATFORM_CONFIG
    key_map = _config_to_env_keys()
    return {
        "base_url": cfg.get("base_url", ""),
        "cookie": cfg.get("cookie", ""),
        "authorization": cfg.get("authorization", ""),
        "course_id": cfg.get("course_id", ""),
        "train_task_id": cfg.get("train_task_id", ""),
        "start_node_id": cfg.get("start_node_id", ""),
        "end_node_id": cfg.get("end_node_id", ""),
    }


class PlatformConfigUpdate(BaseModel):
    base_url: Optional[str] = None
    cookie: Optional[str] = None
    authorization: Optional[str] = None
    course_id: Optional[str] = None
    train_task_id: Optional[str] = None
    start_node_id: Optional[str] = None
    end_node_id: Optional[str] = None


@router.post("/config")
def save_platform_config(body: PlatformConfigUpdate):
    """保存智慧树平台配置到 .env，并更新当前进程的 config。"""
    env_path = _env_path()
    key_map = _config_to_env_keys()
    updates = body.model_dump(exclude_none=True)
    env_keys_to_value = {}
    for cfg_key, env_key in key_map.items():
        if cfg_key in updates:
            v = updates[cfg_key]
            env_keys_to_value[env_key] = (v or "").strip() if v is not None else ""

    if not env_keys_to_value:
        return {"message": "无变更"}

    # 读取现有 .env
    lines = []
    if os.path.isfile(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    # 替换已有键或追加
    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", stripped)
        if m:
            key = m.group(1)
            if key in env_keys_to_value:
                new_lines.append(f'{key}={env_keys_to_value[key]}\n')
                updated_keys.add(key)
                continue
        new_lines.append(line)

    for env_key, val in env_keys_to_value.items():
        if env_key not in updated_keys:
            new_lines.append(f"{env_key}={val}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # 重新加载并更新 config 模块中的 PLATFORM_CONFIG
    from dotenv import load_dotenv
    load_dotenv(env_path, override=True)
    import config
    for cfg_key, env_key in key_map.items():
        if env_key in env_keys_to_value:
            config.PLATFORM_CONFIG[cfg_key] = os.getenv(env_key, DEFAULTS.get(env_key, ""))

    return {"message": "已保存，当前注入将使用新配置"}