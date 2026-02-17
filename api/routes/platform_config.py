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


class LoadConfigRequest(BaseModel):
    """加载配置：从 URL 提取课程/任务 ID，与传入字段合并后保存。"""
    url: Optional[str] = None
    authorization: Optional[str] = None
    cookie: Optional[str] = None
    start_node_id: Optional[str] = None
    end_node_id: Optional[str] = None
    base_url: Optional[str] = None
    course_id: Optional[str] = None
    train_task_id: Optional[str] = None


def _extract_ids_from_url(url: str) -> tuple:
    """从 URL 提取 course_id 和 train_task_id。"""
    course_match = re.search(r"agent-course-full/([^/]+)", url)
    task_match = re.search(r"trainTaskId=([^&]+)", url)
    cid = course_match.group(1) if course_match else None
    tid = task_match.group(1) if task_match else None
    return (cid, tid)


@router.post("/load-config")
def load_platform_config(
    body: LoadConfigRequest, workspace_id: str = Depends(require_workspace_owned)
):
    """
    加载并保存平台配置。输入 url、jwt、cookie、开始节点、结束节点，
    从 URL 提取 course_id/train_task_id，合并后保存到工作区。
    """
    path = _workspace_config_path(workspace_id)
    current = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                current = json.load(f)
        except Exception:
            pass
    # 确保所有 key 存在
    for k in CFG_KEYS:
        if k not in current:
            current[k] = PLATFORM_CONFIG.get(k, "") or ""
    # 若提供 URL，提取 course_id、train_task_id
    if body.url and body.url.strip():
        cid, tid = _extract_ids_from_url(body.url.strip())
        if cid:
            current["course_id"] = cid
        if tid:
            current["train_task_id"] = tid
    # 覆盖用户输入的字段
    if body.authorization is not None:
        current["authorization"] = (body.authorization or "").strip()
    if body.cookie is not None:
        current["cookie"] = (body.cookie or "").strip()
    if body.start_node_id is not None:
        current["start_node_id"] = (body.start_node_id or "").strip()
    if body.end_node_id is not None:
        current["end_node_id"] = (body.end_node_id or "").strip()
    if body.base_url is not None:
        current["base_url"] = (body.base_url or "").strip() or "https://cloudapi.polymas.com"
    if body.course_id is not None:
        current["course_id"] = (body.course_id or "").strip()
    if body.train_task_id is not None:
        current["train_task_id"] = (body.train_task_id or "").strip()
    if not current.get("base_url"):
        current["base_url"] = "https://cloudapi.polymas.com"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    return {**current, "message": "已加载并保存配置"}


@router.post("/set-project")
def set_project_from_url(body: SetProjectRequest, workspace_id: str = Depends(require_workspace_owned)):
    """从智慧树页面 URL 提取课程 ID、训练任务 ID，并可选写入当前工作区配置。"""
    url = (body.url or "").strip()
    if not url:
        raise BadRequestError("请提供 URL")
    course_id, train_task_id = _extract_ids_from_url(url)
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
