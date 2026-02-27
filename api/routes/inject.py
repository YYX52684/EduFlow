# -*- coding: utf-8 -*-
"""
平台注入 API：预览解析结果、执行注入到智慧树平台。使用当前工作区平台配置与卡片路径。
"""
import os
import json
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Tuple, List, Dict, Any

router = APIRouter()

from config import PLATFORM_ENDPOINTS
from api_platform import PlatformAPIClient, CardInjector
from api.routes.auth import require_workspace_owned
from api.routes.platform_config import get_merged_platform_config, check_platform_config_keys
from api.workspace import resolve_workspace_path
from api.exceptions import ConfigError, NotFoundError, PlatformAPIError


def _create_client(cfg: Dict[str, Any]) -> PlatformAPIClient:
    client = PlatformAPIClient(cfg)
    client.set_endpoints(PLATFORM_ENDPOINTS)
    return client


class InjectPreviewRequest(BaseModel):
    cards_path: str


class InjectRunRequest(BaseModel):
    cards_path: str
    task_name: Optional[str] = None
    description: Optional[str] = None


@router.post("/preview")
def inject_preview(req: InjectPreviewRequest, workspace_id: str = Depends(require_workspace_owned)):
    """预览卡片解析结果，不实际调用平台 API。"""
    md_path = resolve_workspace_path(workspace_id, req.cards_path, kind="output", must_exist=True)
    cfg = get_merged_platform_config(workspace_id)
    try:
        client = _create_client(cfg)
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
        raise NotFoundError("卡片文件不存在", details={"path": req.cards_path, "reason": str(e)})
    except Exception as e:
        raise PlatformAPIError("预览解析失败", details={"reason": str(e)})


@router.post("/run")
def inject_run(req: InjectRunRequest, workspace_id: str = Depends(require_workspace_owned)):
    """执行注入：将卡片推送到智慧树平台。使用当前工作区平台配置。"""
    md_path = resolve_workspace_path(workspace_id, req.cards_path, kind="output", must_exist=True)
    cfg = get_merged_platform_config(workspace_id)
    ok, missing = check_platform_config_keys(cfg)
    if not ok:
        raise ConfigError(
            f"平台配置不完整，缺少: {', '.join(missing)}。请在本页「平台配置」中填写并保存。",
            details={"missing": missing},
        )
    try:
        client = _create_client(cfg)
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
        raise NotFoundError("卡片文件不存在", details={"path": req.cards_path, "reason": str(e)})
    except Exception as e:
        raise PlatformAPIError("注入失败", details={"reason": str(e)})
