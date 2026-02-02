"""
Trainset / Dev set 构建与加载
从剧本文件或目录解析出 (full_script, stages) 列表，供 DSPy 优化使用。
支持保存/加载为 JSON，以及结构校验与评估标准对齐检查。
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from parsers import parse_markdown, parse_docx, parse_pdf
from .content_splitter import ContentSplitter

from config import DEEPSEEK_API_KEY


# ---------- 结构约定（与 ContentSplitter 输出及 DSPy 输入一致） ----------
TRAINSET_EXAMPLE_KEYS = {"full_script", "stages"}
STAGE_REQUIRED_KEYS = {"id", "title", "description", "role", "task", "key_points", "content_excerpt"}
STAGE_OPTIONAL_KEYS = {"interaction_rounds", "student_role"}

# 外部评估常见维度对应的剧本应含内容（用于对齐检查提示）
EVAL_ALIGNMENT_HINTS = {
    "任务目标": ["任务目标", "目标"],
    "评分标准": ["评分标准", "满分", "分"],
    "角色与场景": ["角色", "人设", "场景"],
    "阶段目标": ["task", "key_points"],
}


def _get_parser_for_path(file_path: str):
    """根据文件扩展名返回解析器函数。"""
    ext = os.path.splitext(file_path)[1].lower()
    parsers = {
        ".md": parse_markdown,
        ".docx": parse_docx,
        ".pdf": parse_pdf,
    }
    if ext not in parsers:
        raise ValueError(f"不支持的文件格式: {ext}。支持: {', '.join(parsers.keys())}")
    return parsers[ext]


def _parse_content(file_path: str) -> str:
    """解析单个文件得到原始文本内容。"""
    path = os.path.abspath(file_path)
    parser = _get_parser_for_path(path)
    return parser(path)


def build_trainset_from_path(
    path: str,
    api_key: Optional[str] = None,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """
    从单个文件或目录构建 trainset。

    每条样本为 {"full_script": str, "stages": list}，其中 stages 为 ContentSplitter.analyze 返回的格式。

    Args:
        path: 文件路径或目录路径。目录时将递归查找 .md / .docx / .pdf。
        api_key: DeepSeek API 密钥（用于 ContentSplitter.analyze）；不传则用 config。
        verbose: 是否打印进度。

    Returns:
        样本列表，每项含 full_script 与 stages。
    """
    path = os.path.abspath(path)
    api_key = api_key or DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError("未提供 API 密钥，请在 .env 中设置 DEEPSEEK_API_KEY 或传入 api_key")

    files: List[str] = []
    if os.path.isfile(path):
        files = [path]
    elif os.path.isdir(path):
        for ext in (".md", ".docx", ".pdf"):
            for f in Path(path).rglob(f"*{ext}"):
                files.append(str(f))
        files.sort()
    else:
        raise FileNotFoundError(f"路径不存在: {path}")

    if not files:
        raise ValueError(f"未在目录下找到 .md / .docx / .pdf 文件: {path}")

    splitter = ContentSplitter(api_key=api_key)
    examples: List[Dict[str, Any]] = []

    for i, fp in enumerate(files):
        if verbose:
            print(f"  [trainset] 处理 {i + 1}/{len(files)}: {os.path.basename(fp)}")
        try:
            content = _parse_content(fp)
            analysis = splitter.analyze(content)
            stages = analysis.get("stages", [])
            if not stages:
                if verbose:
                    print(f"    [跳过] 未识别出阶段: {fp}")
                continue
            examples.append({
                "full_script": content,
                "stages": stages,
                "source_file": fp,
            })
        except Exception as e:
            if verbose:
                print(f"    [错误] {fp}: {e}")
            raise

    return examples


def save_trainset(examples: List[Dict[str, Any]], json_path: str) -> None:
    """将样本列表保存为 JSON。stages 等可序列化结构原样写入。"""
    path = os.path.abspath(json_path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(examples, f, ensure_ascii=False, indent=2)


def load_trainset(json_path: str) -> List[Dict[str, Any]]:
    """从 JSON 文件加载样本列表。"""
    path = os.path.abspath(json_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"trainset 文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_trainset(
    examples: List[Dict[str, Any]],
    strict: bool = False,
    check_eval_alignment: bool = True,
) -> Tuple[bool, List[str]]:
    """
    校验 trainset 结构与评估标准对齐情况。

    - 结构：每条样本必须有 full_script、stages；每个 stage 必须有 id, title, description, role, task, key_points, content_excerpt。
    - 对齐（可选）：full_script 建议包含任务目标/评分标准等，便于外部评估维度（知识点覆盖率、环节准出等）有据可依。

    Args:
        examples: 样本列表（load_trainset 或 build_trainset_from_path 的返回值）。
        strict: 若 True，任一项不通过即返回 valid=False；否则仅收集所有问题，结构齐全即 valid=True。
        check_eval_alignment: 是否做评估对齐的轻量检查（full_script 是否含任务目标/评分标准等）。

    Returns:
        (valid, messages): valid 表示是否通过；messages 为错误/警告列表。
    """
    messages: List[str] = []
    valid = True

    if not examples:
        messages.append("[错误] trainset 为空")
        return False, messages

    for idx, ex in enumerate(examples):
        if not isinstance(ex, dict):
            messages.append(f"样本 {idx + 1}: 应为 dict，实际为 {type(ex).__name__}")
            valid = False
            continue

        # 顶层键
        missing_top = TRAINSET_EXAMPLE_KEYS - set(ex.keys())
        if missing_top:
            messages.append(f"样本 {idx + 1}: 缺少键 {missing_top}")
            valid = False

        full_script = ex.get("full_script")
        stages = ex.get("stages")

        if full_script is not None and not isinstance(full_script, str):
            messages.append(f"样本 {idx + 1}: full_script 应为 str")
            valid = False
        if stages is not None and not isinstance(stages, list):
            messages.append(f"样本 {idx + 1}: stages 应为 list")
            valid = False

        if not stages:
            if full_script is not None:
                messages.append(f"样本 {idx + 1}: stages 为空，无法生成卡片")
            valid = False
            continue

        # 每个 stage 的必填字段
        for s_idx, stage in enumerate(stages):
            if not isinstance(stage, dict):
                messages.append(f"样本 {idx + 1} 阶段 {s_idx + 1}: 应为 dict")
                valid = False
                continue
            missing_stage = STAGE_REQUIRED_KEYS - set(stage.keys())
            if missing_stage:
                messages.append(f"样本 {idx + 1} 阶段 {s_idx + 1}: 缺少 {missing_stage}")
                if strict:
                    valid = False
            # 非空检查
            for key in ("title", "task", "key_points", "content_excerpt"):
                val = stage.get(key)
                if val is None or (key == "key_points" and (not isinstance(val, list) or len(val) == 0)):
                    if key == "key_points":
                        messages.append(f"样本 {idx + 1} 阶段 {s_idx + 1}: key_points 应为非空列表")
                    else:
                        messages.append(f"样本 {idx + 1} 阶段 {s_idx + 1}: {key} 为空")
                    if strict:
                        valid = False

        # 评估对齐：full_script 建议包含任务目标、评分标准等
        if check_eval_alignment and full_script and isinstance(full_script, str):
            if "任务目标" not in full_script and "目标" not in full_script:
                messages.append(f"样本 {idx + 1}: [建议] full_script 中未见「任务目标」类表述，评估时「目标达成度」等维度可能缺少依据")
            if "评分标准" not in full_script and "满分" not in full_script:
                messages.append(f"样本 {idx + 1}: [建议] full_script 中未见「评分标准」或「满分」，与外部评估维度对齐时可补充")

    if strict and messages:
        valid = False
    elif not valid:
        pass  # 已因结构错误设为 False
    else:
        valid = not any(m.startswith("[错误]") for m in messages)

    return valid, messages


def check_trainset_file(json_path: str, strict: bool = False, check_eval_alignment: bool = True) -> Tuple[bool, List[str]]:
    """
    加载指定 JSON 后执行 validate_trainset，便于 CLI 或脚本调用。

    Returns:
        (valid, messages)
    """
    examples = load_trainset(json_path)
    return validate_trainset(examples, strict=strict, check_eval_alignment=check_eval_alignment)
