"""
框架库：发现并导出所有可用生成框架
开发者可在本目录下新增子目录，实现约定接口后即可被自动发现
"""
import os
import importlib.util
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Type

from .base import BaseCardGenerator


def _frameworks_dir() -> Path:
    return Path(__file__).resolve().parent


def _discover_frameworks() -> List[Dict[str, Any]]:
    """扫描 frameworks/ 下子目录，收集符合约定的框架"""
    frameworks: List[Dict[str, Any]] = []
    root = _frameworks_dir()

    for item in root.iterdir():
        if not item.is_dir():
            continue
        if item.name.startswith("_"):
            continue
        init_py = item / "__init__.py"
        if not init_py.exists():
            continue

        try:
            spec = importlib.util.spec_from_file_location(
                f"generators.frameworks.{item.name}", init_py
            )
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            fid = getattr(mod, "FRAMEWORK_ID", None)
            name = getattr(mod, "FRAMEWORK_NAME", None)
            desc = getattr(mod, "FRAMEWORK_DESCRIPTION", "")
            cls = getattr(mod, "GeneratorClass", None)

            if fid is None or name is None or cls is None:
                continue
            if not isinstance(cls, type) or not issubclass(cls, BaseCardGenerator):
                continue

            frameworks.append({
                "id": fid,
                "name": name,
                "description": desc or "",
                "class": cls,
            })
        except Exception:
            continue

    return frameworks


# 缓存发现结果，避免重复扫描
_cached_list: Optional[List[Dict[str, Any]]] = None


def list_frameworks() -> List[Dict[str, Any]]:
    """
    返回所有可用框架列表
    每项含 id, name, description, class
    """
    global _cached_list
    if _cached_list is None:
        _cached_list = _discover_frameworks()
    return _cached_list


def get_framework(framework_id: str) -> Tuple[Type[BaseCardGenerator], Dict[str, Any]]:
    """
    根据 id 获取框架类及其元信息

    Args:
        framework_id: 框架唯一标识（如 "default", "dspy"）

    Returns:
        (GeneratorClass, meta) 其中 meta 含 id, name, description

    Raises:
        ValueError: 未找到对应框架
    """
    for meta in list_frameworks():
        if meta["id"] == framework_id:
            return meta["class"], {
                "id": meta["id"],
                "name": meta["name"],
                "description": meta["description"],
            }
    available = [m["id"] for m in list_frameworks()]
    raise ValueError(
        f"未找到生成框架: {framework_id}。可用框架: {', '.join(available)}"
    )


def clear_framework_cache() -> None:
    """清除框架列表缓存（用于测试或动态加载新框架后刷新）"""
    global _cached_list
    _cached_list = None


__all__ = [
    "BaseCardGenerator",
    "list_frameworks",
    "get_framework",
    "clear_framework_cache",
]
