# -*- coding: utf-8 -*-
import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

from simulator import SessionRunner, SessionConfig
from api.workspace import get_workspace_id, get_workspace_dirs, resolve_workspace_path
from simulator.session_runner import SessionMode
from simulator.evaluator import EvaluatorFactory


class SimulateRequest(BaseModel):
    cards_path: str
    persona_id: str = "excellent"
    mode: str = "auto"
    output_dir: str = "simulator_output"
    run_evaluation: bool = True


@router.post("/run")
def run_simulation(req: SimulateRequest, workspace_id: str = Depends(get_workspace_id)):
    """运行学生模拟测试（仅支持 auto 模式），卡片与输出均在当前工作区。"""
    md_path = resolve_workspace_path(workspace_id, req.cards_path, kind="output")
    if not os.path.exists(md_path):
        raise HTTPException(status_code=404, detail=f"卡片文件不存在: {req.cards_path}")
    if req.mode not in ("auto", "manual", "hybrid"):
        req = req.model_copy(update={"mode": "auto"})
    if req.mode != "auto":
        raise HTTPException(
            status_code=400,
            detail="Web API 暂仅支持 auto 模式；manual/hybrid 请使用命令行 python main.py --simulate ...",
        )
    _, output_dir, _ = get_workspace_dirs(workspace_id)
    run_output = os.path.join(output_dir, req.output_dir)
    config = SessionConfig(
        mode=SessionMode(req.mode),
        persona_id=req.persona_id,
        output_dir=run_output,
        verbose=False,
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
