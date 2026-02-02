"""
外部评估指标适配层
从指定导出文件中解析出标量分数，供 DSPy 优化器使用。
支持 JSON、CSV、Markdown（智能体评测报告）及自定义解析器。
"""

import os
import re
import json
import csv
from pathlib import Path
from typing import Optional, Callable, Any, Dict


# 默认配置（可被 config 覆盖）
DEFAULT_EXPORT_FILE_PATH = ""
DEFAULT_PARSER = "json"
DEFAULT_JSON_SCORE_KEY = "total_score"


def _parse_json(path: str, score_key: str = DEFAULT_JSON_SCORE_KEY, **kwargs: Any) -> float:
    """从 JSON 文件读取指定键的数值分数。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    value = data.get(score_key)
    if value is None:
        raise KeyError(f"JSON 中未找到键: {score_key}")
    try:
        return float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"分数字段 '{score_key}' 无法转为数值: {value}") from e


def _parse_csv(
    path: str,
    score_column: Optional[str] = None,
    score_column_index: Optional[int] = None,
    **kwargs: Any,
) -> float:
    """从 CSV 文件读取分数：按列名或列索引取第一行对应列。"""
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        raise ValueError("CSV 文件为空")
    header = rows[0]
    data_row = rows[1] if len(rows) > 1 else rows[0]
    if score_column is not None:
        if score_column not in header:
            raise KeyError(f"CSV 中未找到列: {score_column}")
        idx = header.index(score_column)
    elif score_column_index is not None:
        idx = score_column_index
    else:
        idx = 0
    if idx >= len(data_row):
        raise ValueError(f"CSV 行数据不足，列索引 {idx}")
    raw = data_row[idx].strip()
    try:
        return float(raw)
    except ValueError as e:
        raise ValueError(f"CSV 分数列无法转为数值: {raw}") from e


def _parse_markdown(path: str, **kwargs: Any) -> float:
    """
    从 Markdown 格式的智能体评测报告中解析总分。
    支持格式示例：
    - **总分**: 56.0 / 100
    - 总分: 56.0 / 100
    - 评测完成。总分: 56.0
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # 优先匹配 "- **总分**: 56.0 / 100" 或 "**总分**: 56.0 / 100"
    m = re.search(r"\*\*总分\*\*\s*[：:]\s*(\d+(?:\.\d+)?)\s*(?:/\s*\d+)?", content)
    if m:
        return float(m.group(1))
    # 匹配 "总分: 56.0" 或 "总分：56.0"
    m = re.search(r"总分\s*[：:]\s*(\d+(?:\.\d+)?)\s*(?:/\s*\d+)?", content)
    if m:
        return float(m.group(1))
    # 匹配 "评测完成。总分: 56.0"
    m = re.search(r"评测完成[。.]\s*总分\s*[：:]\s*(\d+(?:\.\d+)?)", content)
    if m:
        return float(m.group(1))
    raise ValueError("Markdown 中未找到总分字段（需包含「总分」及数字，如 - **总分**: 56.0 / 100）")


def get_score_from_export(
    export_path: Optional[str] = None,
    *,
    export_file_path: Optional[str] = None,
    parser: str = "json",
    parser_kwargs: Optional[Dict[str, Any]] = None,
    custom_parser: Optional[Callable[[str], float]] = None,
    return_zero_on_missing: bool = True,
) -> float:
    """
    从导出文件中解析出标量分数。

    Args:
        export_path: 导出文件路径（优先使用；未传则用 export_file_path）。
        export_file_path: 配置的导出文件路径（当 export_path 为 None 时使用）。
        parser: 解析器类型，"json" | "csv" | "md"（Markdown 智能体评测报告）| "custom"。
        parser_kwargs: 解析器额外参数。JSON 常用 score_key；CSV 常用 score_column 或 score_column_index。
        custom_parser: 当 parser="custom" 时使用的函数，签名为 (path: str) -> float。
        return_zero_on_missing: 文件不存在或解析失败时是否返回 0（否则抛出异常）。

    Returns:
        解析得到的分数（float）。
    """
    path = export_path or export_file_path or DEFAULT_EXPORT_FILE_PATH
    path = os.path.abspath(path) if path else ""
    parser_kwargs = parser_kwargs or {}

    if not path:
        if return_zero_on_missing:
            return 0.0
        raise FileNotFoundError("未配置导出文件路径，且未传入 export_path")
    if not os.path.isfile(path):
        if return_zero_on_missing:
            return 0.0
        raise FileNotFoundError(f"导出文件不存在: {path}")

    try:
        if parser == "json":
            return _parse_json(path, **parser_kwargs)
        if parser == "csv":
            return _parse_csv(path, **parser_kwargs)
        if parser in ("md", "markdown"):
            return _parse_markdown(path, **parser_kwargs)
        if parser == "custom":
            if custom_parser is None:
                raise ValueError("parser='custom' 时必须提供 custom_parser")
            return custom_parser(path)
        raise ValueError(f"不支持的 parser 类型: {parser}")
    except (KeyError, ValueError, FileNotFoundError) as e:
        if return_zero_on_missing:
            return 0.0
        raise e


def load_config_from_dict(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    从配置字典中加载外部指标相关项，供 get_score_from_export 使用。

    期望的键：export_file_path, parser, json_score_key, csv_score_column, csv_score_column_index, custom_parser.
    """
    return {
        "export_file_path": config.get("export_file_path", DEFAULT_EXPORT_FILE_PATH),
        "parser": config.get("parser", DEFAULT_PARSER),
        "parser_kwargs": {
            k: v
            for k, v in {
                "score_key": config.get("json_score_key", DEFAULT_JSON_SCORE_KEY),
                "score_column": config.get("csv_score_column"),
                "score_column_index": config.get("csv_score_column_index"),
            }.items()
            if v is not None
        },
        "custom_parser": config.get("custom_parser"),
        "return_zero_on_missing": config.get("return_zero_on_missing", True),
    }
