# -*- coding: utf-8 -*-
"""
智慧树平台配置：按工作区读写（workspaces/<id>/platform_config.json），注入时使用该配置。
"""
import os
import re
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from config import PLATFORM_CONFIG
from api.workspace import get_workspace_id, get_workspace_dirs


def _load_env_config() -> dict:
    """重新加载 .env 并返回平台配置（供 reset-to-env 使用）。"""
    from dotenv import load_dotenv
    load_dotenv(override=True)
    return {
        "base_url": os.getenv("PLATFORM_BASE_URL", "https://cloudapi.polymas.com"),
        "cookie": os.getenv("PLATFORM_COOKIE", ""),
        "authorization": os.getenv("PLATFORM_AUTHORIZATION", ""),
        "course_id": os.getenv("PLATFORM_COURSE_ID", ""),
        "train_task_id": os.getenv("PLATFORM_TRAIN_TASK_ID", ""),
        "start_node_id": os.getenv("PLATFORM_START_NODE_ID", ""),
        "end_node_id": os.getenv("PLATFORM_END_NODE_ID", ""),
    }

CFG_KEYS = ["base_url", "cookie", "authorization", "course_id", "train_task_id", "start_node_id", "end_node_id"]


def _workspace_config_path(workspace_id: str) -> str:
    _, _, workspace_root = get_workspace_dirs(workspace_id)
    return os.path.join(workspace_root, "platform_config.json")


@router.get("/config")
def get_platform_config(workspace_id: str = Depends(get_workspace_id)):
    """返回当前工作区智慧树平台配置；无则回退到服务端 .env。"""
    path = _workspace_config_path(workspace_id)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return {k: cfg.get(k, "") for k in CFG_KEYS}
        except Exception:
            pass
    return {k: PLATFORM_CONFIG.get(k, "") for k in CFG_KEYS}


class PlatformConfigUpdate(BaseModel):
    base_url: Optional[str] = None
    cookie: Optional[str] = None
    authorization: Optional[str] = None
    course_id: Optional[str] = None
    train_task_id: Optional[str] = None
    start_node_id: Optional[str] = None
    end_node_id: Optional[str] = None


@router.post("/config")
def save_platform_config(body: PlatformConfigUpdate, workspace_id: str = Depends(get_workspace_id)):
    """保存到当前工作区，仅更新提交的字段。"""
    path = _workspace_config_path(workspace_id)
    current = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                current = json.load(f)
        except Exception:
            pass
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"message": "无变更"}
    for k in CFG_KEYS:
        if k in updates:
            v = updates[k]
            current[k] = (v or "").strip() if v is not None else ""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    return {"message": "已保存，本工作区注入将使用此配置"}


class SetProjectRequest(BaseModel):
    url: str
    save: bool = True  # 是否写入当前工作区配置


@router.post("/reset-to-env")
def reset_platform_config_to_env(workspace_id: str = Depends(get_workspace_id)):
    """用当前 .env 中的平台配置覆盖工作区配置，解决「修改了 .env 但注入仍用旧配置」的问题。会重新读取 .env，无需重启服务。"""
    path = _workspace_config_path(workspace_id)
    cfg = _load_env_config()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return {"message": "已用 .env 配置覆盖工作区"}


@router.post("/set-project")
def set_project_from_url(body: SetProjectRequest, workspace_id: str = Depends(get_workspace_id)):
    """从智慧树页面 URL 提取课程 ID、训练任务 ID，并可选写入当前工作区配置。"""
    url = (body.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="请提供 URL")
    course_match = re.search(r"agent-course-full/([^/]+)", url)
    task_match = re.search(r"trainTaskId=([^&]+)", url)
    course_id = course_match.group(1) if course_match else None
    train_task_id = task_match.group(1) if task_match else None
    if not course_id:
        raise HTTPException(
            status_code=400,
            detail="无法从 URL 提取课程 ID，请确保包含 agent-course-full/<课程ID>",
        )
    if not train_task_id:
        raise HTTPException(
            status_code=400,
            detail="无法从 URL 提取训练任务 ID，请确保 URL 包含 trainTaskId= 参数",
        )
    result = {"course_id": course_id, "train_task_id": train_task_id}
    if body.save:
        path = _workspace_config_path(workspace_id)
        current = {}
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    current = json.load(f)
            except Exception:
                pass
        current["course_id"] = course_id
        current["train_task_id"] = train_task_id
        with open(path, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        result["message"] = "已写入当前工作区配置"
    return result
