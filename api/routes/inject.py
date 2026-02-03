# -*- coding: utf-8 -*-
"""
平台注入 API：预览解析结果、执行注入到智慧树平台。
"""
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Tuple, List

router = APIRouter()

from config import PLATFORM_CONFIG, PLATFORM_ENDPOINTS
from api_platform import PlatformAPIClient, CardInjector


def _check_platform_config() -> Tuple[bool, List[str]]:
    """返回 (是否完整, 缺失项列表)"""
    missing = []
    if not PLATFORM_CONFIG.get("cookie"):
        missing.append("PLATFORM_COOKIE")
    if not PLATFORM_CONFIG.get("authorization"):
        missing.append("PLATFORM_AUTHORIZATION")
    if not PLATFORM_CONFIG.get("course_id"):
        missing.append("PLATFORM_COURSE_ID")
    if not PLATFORM_CONFIG.get("train_task_id"):
        missing.append("PLATFORM_TRAIN_TASK_ID")
    if not PLATFORM_CONFIG.get("start_node_id"):
        missing.append("PLATFORM_START_NODE_ID")
    if not PLATFORM_CONFIG.get("end_node_id"):
        missing.append("PLATFORM_END_NODE_ID")
    return (len(missing) == 0, missing)


def _create_client() -> PlatformAPIClient:
    client = PlatformAPIClient(PLATFORM_CONFIG)
    client.set_endpoints(PLATFORM_ENDPOINTS)
    return client


class InjectPreviewRequest(BaseModel):
    cards_path: str


class InjectRunRequest(BaseModel):
    cards_path: str
    task_name: Optional[str] = None
    description: Optional[str] = None


def _resolve_path(path: str) -> str:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return path if os.path.isabs(path) else os.path.join(root, path)


@router.post("/preview")
def inject_preview(req: InjectPreviewRequest):
    """预览卡片解析结果，不实际调用平台 API。"""
    md_path = _resolve_path(req.cards_path)
    if not os.path.exists(md_path):
        raise HTTPException(status_code=404, detail=f"卡片文件不存在: {req.cards_path}")
    try:
        client = _create_client()
        injector = CardInjector(client)
        all_cards = injector.parse_markdown(md_path)
        a_cards, b_cards = injector.separate_cards(all_cards)
        a_list = []
        for c in a_cards:
            fmt = c.to_a_card_format()
            a_list.append({
                "card_id": c.card_id,
                "title": c.title,
                "step_name": fmt["step_name"],
                "stage_description": (c.stage_description or "")[:100],
                "interaction_rounds": fmt["interaction_rounds"],
            })
        b_list = []
        for c in b_cards:
            b_list.append({
                "card_id": c.card_id,
                "title": c.title,
            })
        return {
            "file": req.cards_path,
            "total_a": len(a_cards),
            "total_b": len(b_cards),
            "a_cards": a_list,
            "b_cards": b_list,
            "summary": f"将创建 {len(a_cards)} 个节点、{max(0, len(a_cards)-1)} 条连线并设置 {len(b_cards)} 个过渡提示词",
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
def inject_run(req: InjectRunRequest):
    """执行注入：将卡片推送到智慧树平台。需在 .env 中配置平台相关项。"""
    md_path = _resolve_path(req.cards_path)
    if not os.path.exists(md_path):
        raise HTTPException(status_code=404, detail=f"卡片文件不存在: {req.cards_path}")
    ok, missing = _check_platform_config()
    if not ok:
        raise HTTPException(
            status_code=400,
            detail=f"平台配置不完整，缺少: {', '.join(missing)}。请在 .env 中配置后重试。",
        )
    try:
        client = _create_client()
        injector = CardInjector(client)

        def _progress(current: int, total: int, message: str):
            pass

        result = injector.inject_with_config(
            md_path,
            task_name=req.task_name,
            description=req.description,
            progress_callback=_progress,
        )
        a_ok = result["successful_a_cards"] == result["total_a_cards"]
        expected_b = result["total_a_cards"] - 1
        b_ok = result["successful_b_cards"] >= expected_b
        success = a_ok and b_ok
        return {
            "success": success,
            "total_a_cards": result["total_a_cards"],
            "successful_a_cards": result["successful_a_cards"],
            "total_b_cards": result["total_b_cards"],
            "successful_b_cards": result["successful_b_cards"],
            "evaluation_items_count": result.get("evaluation_items_count"),
            "total_score": result.get("total_score"),
            "message": "注入成功" if success else "部分注入失败，请查看上述数量",
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
