# -*- coding: utf-8 -*-
import json
import os
import re
from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple

router = APIRouter()

from simulator import evaluate_session
from simulator.evaluator import EvaluatorFactory
from api.routes.auth import require_workspace_owned
from api.workspace import get_project_dirs, get_workspace_dirs, resolve_workspace_path
from api.exceptions import BadRequestError, LLMError


def _parse_dialogue_from_content(content: bytes, filename: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    从文件内容解析出 dialogue 与 session_id。
    支持：.json（标准会话日志）；.txt 为 JSON 时按 JSON 解析，否则按纯文本对话解析。
    纯文本格式：每行 "学生: ..." 或 "NPC: ..." 或 "**[学生]**: ..." 等，解析为 dialogue 列表。
    """
    text = content.decode("utf-8").strip()
    ext = (filename or "").lower()
    if ext.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise BadRequestError("JSON 解析失败", details={"reason": str(e)})
        dialogue = data.get("dialogue", [])
        session_id = data.get("session_id", "unknown")
        return dialogue, session_id
    if ext.endswith(".txt"):
        # 先尝试整段为 JSON（有人把 JSON 存成 .txt）
        try:
            data = json.loads(text)
            dialogue = data.get("dialogue", [])
            session_id = data.get("session_id", "unknown")
            return dialogue, session_id
        except json.JSONDecodeError:
            pass
        # 按纯文本对话解析：行首为 "学生: xxx" / "NPC: xxx" / "**[学生]**: xxx" / "第N轮 [NPC]: xxx" 等
        dialogue = []
        turn = 0
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            # 去掉 "第N轮 "、"**"、方括号，再按 ": " 或 "：" 分割
            normalized = re.sub(r"^第\d+轮\s*", "", s)
            normalized = re.sub(r"^\*\*|\*\*$", "", normalized.strip())
            normalized = re.sub(r"^\[|\]$", "", normalized.strip())
            idx = re.search(r"\s*[:：]\s*", normalized)
            if idx:
                role_part = normalized[: idx.start()].strip()
                content = normalized[idx.end() :].strip()
                if role_part and content:
                    role_lower = role_part.lower()
                    speaker = "student" if "学生" in role_part or role_lower == "user" else "npc"
                    turn += 1
                    dialogue.append({"turn": turn, "speaker": speaker, "content": content})
        session_id = "from_txt"
        if not dialogue:
            raise BadRequestError("未能从 .txt 中解析出对话记录，请使用「学生: ...」或「NPC: ...」格式")
        return dialogue, session_id
    raise BadRequestError("仅支持 .json 或 .txt 格式的会话日志")


class EvaluateByPathRequest(BaseModel):
    log_path: str
    output_dir: Optional[str] = None
    save_to_export: bool = False  # 保存为 output/optimizer/export_score.json(.md) 供优化器使用


class EvaluateByBodyRequest(BaseModel):
    session_id: str
    dialogue: List[Dict[str, Any]]


def _write_export_files(report, output_dir: str) -> str:
    """将报告写入 output_dir/optimizer/export_score.json 和 .md，返回相对路径如 output/optimizer/export_score.json。"""
    opt_dir = os.path.join(output_dir, "optimizer")
    os.makedirs(opt_dir, exist_ok=True)
    json_path = os.path.join(opt_dir, "export_score.json")
    md_path = os.path.join(opt_dir, "export_score.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report.to_markdown())
    return "output/optimizer/export_score.json"


@router.post("/evaluate")
def evaluate(req: EvaluateByPathRequest, workspace_id: str = Depends(require_workspace_owned)):
    """根据当前工作区内会话日志路径评估，返回报告。可选保存为导出文件供优化器使用。"""
    path = resolve_workspace_path(workspace_id, req.log_path, kind="output", must_exist=True)
    out_dir = None
    if req.output_dir:
        _, output_dir, _ = get_workspace_dirs(workspace_id)
        out_dir = os.path.join(output_dir, req.output_dir)
    try:
        report = evaluate_session(path, output_dir=out_dir)
        result = report.to_dict()
        if req.save_to_export:
            _, project_output, _ = get_project_dirs(workspace_id)
            export_rel = _write_export_files(report, project_output)
            result["saved_export_path"] = export_rel
        return result
    except Exception as e:
        raise LLMError("评估失败", details={"reason": str(e)})


@router.post("/evaluate/from-file")
async def evaluate_from_file(
    workspace_id: str = Depends(require_workspace_owned),
    file: UploadFile = File(...),
    save_to_export: bool = Form(False),
):
    """上传会话日志文件（.json 或 .txt），直接评估并返回报告。.txt 可为 JSON 或「学生: ...」「NPC: ...」格式。"""
    fn = (file.filename or "").lower()
    if not fn.endswith(".json") and not fn.endswith(".txt"):
        raise BadRequestError("请上传 .json 或 .txt 格式的会话日志")
    try:
        content = await file.read()
        dialogue, session_id = _parse_dialogue_from_content(content, file.filename or "")
    except BadRequestError:
        raise
    try:
        evaluator = EvaluatorFactory.create_from_env()
        report = evaluator.evaluate(dialogue, session_id=session_id)
        result = report.to_dict()
        if save_to_export:
            _, project_output, _ = get_project_dirs(workspace_id)
            export_rel = _write_export_files(report, project_output)
            result["saved_export_path"] = export_rel
        return result
    except Exception as e:
        raise LLMError("评估失败", details={"reason": str(e)})


@router.post("/evaluate/from-dialogue")
def evaluate_from_dialogue(req: EvaluateByBodyRequest):
    """根据请求体中的 dialogue 与 session_id 直接评估。"""
    try:
        evaluator = EvaluatorFactory.create_from_env()
        report = evaluator.evaluate(req.dialogue, session_id=req.session_id)
        return report.to_dict()
    except Exception as e:
        raise LLMError("评估失败", details={"reason": str(e)})
