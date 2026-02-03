# -*- coding: utf-8 -*-
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

router = APIRouter()

from simulator import evaluate_session
from simulator.evaluator import EvaluatorFactory


class EvaluateByPathRequest(BaseModel):
    log_path: str
    output_dir: Optional[str] = None


class EvaluateByBodyRequest(BaseModel):
    session_id: str
    dialogue: List[Dict[str, Any]]


@router.post("/evaluate")
def evaluate(req: EvaluateByPathRequest):
    """根据会话日志文件路径评估，返回报告。"""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = req.log_path if os.path.isabs(req.log_path) else os.path.join(root, req.log_path)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"日志文件不存在: {req.log_path}")
    try:
        report = evaluate_session(path, output_dir=req.output_dir)
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate/from-dialogue")
def evaluate_from_dialogue(req: EvaluateByBodyRequest):
    """根据请求体中的 dialogue 与 session_id 直接评估。"""
    try:
        evaluator = EvaluatorFactory.create_from_env()
        report = evaluator.evaluate(req.dialogue, session_id=req.session_id)
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
