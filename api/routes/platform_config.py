# -*- coding: utf-8 -*-
"""
智慧树平台配置：按工作区读写（workspaces/<id>/platform_config.json），注入时使用该配置。
"""
import os
import re
import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from config import PLATFORM_CONFIG
from api.routes.auth import require_workspace_owned
from api.workspace import get_workspace_file_path
from api.exceptions import BadRequestError


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


def get_merged_platform_config(workspace_id: str) -> dict:
    """
    读取平台配置：以 PLATFORM_CONFIG（.env）为底，工作区 JSON 中非空值覆盖。
    注入、校验等需要「最终生效配置」时使用此函数。
    """
    merged = dict(PLATFORM_CONFIG)
    path = get_workspace_file_path(workspace_id, "platform_config.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                ws = json.load(f)
            for k in CFG_KEYS:
                v = ws.get(k)
                if v is not None and str(v).strip():
                    merged[k] = str(v).strip()
        except Exception:
            pass
    return merged


def _workspace_config_path(workspace_id: str) -> str:
    return get_workspace_file_path(workspace_id, "platform_config.json")


@router.get("/config")
def get_platform_config(workspace_id: str = Depends(require_workspace_owned)):
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
def save_platform_config(body: PlatformConfigUpdate, workspace_id: str = Depends(require_workspace_owned)):
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
def reset_platform_config_to_env(workspace_id: str = Depends(require_workspace_owned)):
    """用当前 .env 中的平台配置覆盖工作区配置，解决「修改了 .env 但注入仍用旧配置」的问题。会重新读取 .env，无需重启服务。"""
    path = _workspace_config_path(workspace_id)
    cfg = _load_env_config()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return {"message": "已用 .env 配置覆盖工作区"}


@router.post("/set-project")
def set_project_from_url(body: SetProjectRequest, workspace_id: str = Depends(require_workspace_owned)):
    """从智慧树页面 URL 提取课程 ID、训练任务 ID，并可选写入当前工作区配置。"""
    url = (body.url or "").strip()
    if not url:
        raise BadRequestError("请提供 URL")
    course_match = re.search(r"agent-course-full/([^/]+)", url)
    task_match = re.search(r"trainTaskId=([^&]+)", url)
    course_id = course_match.group(1) if course_match else None
    train_task_id = task_match.group(1) if task_match else None
    if not course_id:
        raise BadRequestError(
            "无法从 URL 提取课程 ID，请确保包含 agent-course-full/<课程ID>",
            details={"url": url[:80]},
        )
    if not train_task_id:
        raise BadRequestError(
            "无法从 URL 提取训练任务 ID，请确保 URL 包含 trainTaskId= 参数",
            details={"url": url[:80]},
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
