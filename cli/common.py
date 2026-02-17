# -*- coding: utf-8 -*-
"""CLI 共用：解析器选择、进度条、平台配置检查与客户端创建。"""
import os
import sys

# 本模块被 main.py 或 run_web 等入口加载时，项目根已在 sys.path
from config import PLATFORM_CONFIG, PLATFORM_ENDPOINTS
from api_platform import PlatformAPIClient

# 延迟导入 parsers，避免 CLI 未用脚本时加载
def get_parser_for_file(file_path: str):
    """根据文件扩展名返回对应的解析器函数。"""
    from parsers import parse_markdown, parse_docx, parse_doc, parse_pdf
    ext = os.path.splitext(file_path)[1].lower()
    parsers = {
        ".md": parse_markdown,
        ".docx": parse_docx,
        ".doc": parse_doc,
        ".pdf": parse_pdf,
    }
    if ext not in parsers:
        raise ValueError(f"不支持的文件格式: {ext}。支持的格式: {', '.join(parsers.keys())}")
    return parsers[ext]


def progress_callback(current: int, total: int, message: str):
    """进度回调，在终端显示进度条。"""
    percentage = int(current / total * 100) if total else 0
    bar_length = 30
    filled_length = int(bar_length * current / total) if total else 0
    bar = "█" * filled_length + "░" * (bar_length - filled_length)
    print(f"\r[{bar}] {percentage}% - {message}", end="", flush=True)
    if total and current == total:
        print()


def check_platform_config() -> bool:
    """检查平台配置是否完整，缺失时打印警告并返回 False。"""
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
        missing.append("PLATFORM_START_NODE_ID (训练开始节点)")
    if not PLATFORM_CONFIG.get("end_node_id"):
        missing.append("PLATFORM_END_NODE_ID (训练结束节点)")
    if missing:
        print("\n[警告] 以下配置项缺失:")
        for item in missing:
            print(f"  - {item}")
        print("\n请在 .env 文件中设置这些配置")
        return False
    return True


def create_platform_client() -> PlatformAPIClient:
    """创建并返回配置好的平台 API 客户端。"""
    client = PlatformAPIClient(PLATFORM_CONFIG)
    client.set_endpoints(PLATFORM_ENDPOINTS)
    return client
