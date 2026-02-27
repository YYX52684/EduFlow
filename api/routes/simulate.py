# -*- coding: utf-8 -*-
import os
import time
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from simulator import SessionRunner, SessionConfig
from simulator.card_loader import LocalCardLoader
from api.routes.auth import require_workspace_owned
from api.workspace import get_workspace_dirs, resolve_workspace_path
from api.routes.llm_config import build_chat_completions_url
from simulator.session_runner import SessionMode
from simulator.evaluator import EvaluatorFactory
from api.routes.llm_config import require_llm_config
from api.exceptions import BadRequestError, NotFoundError, LLMError


def _card_to_parsed_item(card):
    """将 CardData 转为 API 返回的卡片项（含 sections）。"""
    return {
        "card_id": card.card_id,
        "card_type": card.card_type,
        "stage_num": card.stage_num,
        "title": card.title,
        "stage_name": getattr(card, "stage_name", "") or "",
        "sections": {
            "Role": getattr(card, "role", "") or "",
            "Context": getattr(card, "context", "") or "",
            "Interaction": getattr(card, "interaction", "") or "",
            "Transition": getattr(card, "transition", "") or "",
            "Constraints": getattr(card, "constraints", "") or "",
            "Prologue": getattr(card, "prologue", "") or "",
            "Output": getattr(card, "output", "") or "",
        },
        "full_content": getattr(card, "full_content", "") or "",
    }

# 基于内容试玩时写入的临时文件子目录
EDIT_PREVIEW_DIR = "_edit_preview"


class SimulateRequest(BaseModel):
    cards_path: str
    persona_id: str = "excellent"
    mode: str = "auto"
    output_dir: str = "simulator_output"
    run_evaluation: bool = True


class SimulateFromContentRequest(BaseModel):
    cards_content: str
    persona_id: str = "excellent"
    run_evaluation: bool = True


@router.get("/cards-parsed")
def get_cards_parsed(
    path: str,
    workspace_id: str = Depends(require_workspace_owned),
):
    """解析卡片文件，返回按执行顺序排列的卡片列表，供前端平台式分块展示。path 相对 output，如 output/cards_xxx.md。"""
    md_path = resolve_workspace_path(workspace_id, path, kind="output", must_exist=True)
    try:
        loader = LocalCardLoader()
        with open(md_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        cards = loader.parse_markdown_content(content)
        sequence = loader.get_card_sequence(cards)
        return {"cards": [_card_to_parsed_item(c) for c in sequence]}
    except Exception as e:
        raise LLMError("解析卡片失败", details={"reason": str(e)})


@router.post("/run")
def run_simulation(req: SimulateRequest, workspace_id: str = Depends(require_workspace_owned)):
    """运行学生模拟测试（仅支持 auto 模式），卡片与输出均在当前工作区。

    使用当前工作区 LLM 配置（设置中的 API Key + 模型）作为 NPC 与学生 LLM 的统一配置。
    """
    md_path = resolve_workspace_path(workspace_id, req.cards_path, kind="output", must_exist=True)
    if req.mode not in ("auto", "manual", "hybrid"):
        req = req.model_copy(update={"mode": "auto"})
    if req.mode != "auto":
        raise BadRequestError(
            "Web API 暂仅支持 auto 模式；manual/hybrid 请使用命令行 python main.py --simulate ..."
        )
    _, output_dir, _ = get_workspace_dirs(workspace_id)
    run_output = os.path.join(output_dir, req.output_dir)

    llm = require_llm_config(workspace_id)
    api_key = llm.get("api_key") or ""
    base_url = (llm.get("base_url") or "").rstrip("/")
    model_name = llm.get("model") or ""

    api_url = build_chat_completions_url(base_url)
    npc_student_config = {
        "api_url": api_url,
        "api_key": api_key,
        "model": model_name,
        # 其余参数使用各自类中的默认 max_tokens / temperature
    }

    config = SessionConfig(
        mode=SessionMode(req.mode),
        persona_id=req.persona_id,
        output_dir=run_output,
        verbose=False,
        npc_config=npc_student_config,
        student_config=npc_student_config,
    )
    runner = SessionRunner(config)
    runner.load_cards(md_path)
    runner.setup()
    log = runner.run()
    result = {
        "session_id": log.session_id,
        "start_time": log.start_time,
        "end_time": log.end_time,
        "config": log.config,
        "cards_used": log.cards_used,
        "dialogue": [
            {"turn": d.turn_number, "card_id": d.card_id, "speaker": d.speaker, "content": d.content}
            for d in log.dialogue
        ],
        "summary": log.summary,
    }
    if req.run_evaluation and log.summary.get("status") == "completed":
        try:
            evaluator = EvaluatorFactory.create_from_env()
            dialogue = runner.get_dialogue_for_evaluation()
            report = evaluator.evaluate(dialogue, session_id=log.session_id)
            reports_dir = os.path.join(run_output, "reports")
            os.makedirs(reports_dir, exist_ok=True)
            evaluator.save_report(report, reports_dir)
            result["evaluation"] = report.to_dict()
        except Exception as e:
            result["evaluation_error"] = str(e)
    return result


@router.post("/run-from-content")
def run_simulation_from_content(
    req: SimulateFromContentRequest,
    workspace_id: str = Depends(require_workspace_owned),
):
    """基于卡片正文直接试玩，无需先保存文件。将内容写入临时文件后运行仿真，适合编辑后一键试玩。"""
    if not (req.cards_content or req.cards_content.strip()):
        raise BadRequestError("cards_content 不能为空")
    _, output_dir, _ = get_workspace_dirs(workspace_id)
    preview_dir = os.path.join(output_dir, EDIT_PREVIEW_DIR)
    os.makedirs(preview_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    preview_path = os.path.join(preview_dir, f"cards_preview_{ts}.md")
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write(req.cards_content.strip())
    rel_path = f"output/{EDIT_PREVIEW_DIR}/cards_preview_{ts}.md"
    run_output = os.path.join(output_dir, "simulator_output")

    llm = require_llm_config(workspace_id)
    api_key = llm.get("api_key") or ""
    base_url = (llm.get("base_url") or "").rstrip("/")
    model_name = llm.get("model") or ""
    api_url = build_chat_completions_url(base_url)
    npc_student_config = {"api_url": api_url, "api_key": api_key, "model": model_name}

    config = SessionConfig(
        mode=SessionMode.AUTO,
        persona_id=req.persona_id,
        output_dir=run_output,
        verbose=False,
        npc_config=npc_student_config,
        student_config=npc_student_config,
    )
    runner = SessionRunner(config)
    runner.load_cards(preview_path)
    runner.setup()
    log = runner.run()
    result = {
        "session_id": log.session_id,
        "start_time": log.start_time,
        "end_time": log.end_time,
        "config": log.config,
        "cards_used": log.cards_used,
        "preview_path": rel_path,
        "dialogue": [
            {"turn": d.turn_number, "card_id": d.card_id, "speaker": d.speaker, "content": d.content}
            for d in log.dialogue
        ],
        "summary": log.summary,
    }
    if req.run_evaluation and log.summary.get("status") == "completed":
        try:
            evaluator = EvaluatorFactory.create_from_env()
            dialogue = runner.get_dialogue_for_evaluation()
            report = evaluator.evaluate(dialogue, session_id=log.session_id)
            reports_dir = os.path.join(run_output, "reports")
            os.makedirs(reports_dir, exist_ok=True)
            evaluator.save_report(report, reports_dir)
            result["evaluation"] = report.to_dict()
        except Exception as e:
            result["evaluation_error"] = str(e)
    return result
