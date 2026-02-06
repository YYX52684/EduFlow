# -*- coding: utf-8 -*-
"""
课程/项目列表与当前项目切换 API。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.workspace import get_workspace_id, list_projects, set_current_project, get_current_project

router = APIRouter()


@router.get("/list")
def list_projects_api(workspace_id: str = Depends(get_workspace_id)):
    """列出当前工作区下所有项目（课程 + 小项目）。"""
    return {"projects": list_projects(workspace_id)}


@router.get("/current")
def get_current_project_api(workspace_id: str = Depends(get_workspace_id)):
    """获取当前选中的项目。未设置则返回 null。"""
    current = get_current_project(workspace_id)
    return {"current": current}


class SetCurrentProjectRequest(BaseModel):
    course: str
    project: str = ""


@router.put("/current")
def set_current_project_api(req: SetCurrentProjectRequest, workspace_id: str = Depends(get_workspace_id)):
    """切换当前项目。后续脚本解析、卡片、trainset、优化器均在该项目目录下。"""
    set_current_project(workspace_id, req.course, req.project or "")
    return {"current": {"course": req.course, "project": req.project or req.course}}
