# -*- coding: utf-8 -*-
from fastapi import APIRouter
from generators import list_frameworks

router = APIRouter()


@router.get("/frameworks")
def get_frameworks():
    """列出所有可用的卡片生成框架（仅返回 id/name/description，不含类对象）"""
    items = list_frameworks()
    # 不要返回 "class" 键，否则 JSON 序列化会报错（vars/iterable 等）
    frameworks = [
        {"id": m["id"], "name": m.get("name", m["id"]), "description": m.get("description", "")}
        for m in (items or [])
    ]
    return {"frameworks": frameworks}
