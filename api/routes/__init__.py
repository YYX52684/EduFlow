# -*- coding: utf-8 -*-
"""
路由聚合模块。

说明：
- 此包依旧命名为 routes，以保持与历史代码兼容；
- 在总体架构上，它承担「routers」的角色，配合 services/schemas/core/utils 分层。
"""

from . import (  # noqa: F401
    auth,
    cards,
    closed_loop,
    evaluate,
    frameworks,
    health,
    inject,
    input_files,
    llm_config,
    optimizer,
    personas,
    platform_config,
    projects,
    script,
    simulate,
    trainset,
    output_files,
)

__all__ = [
    "auth",
    "cards",
    "closed_loop",
    "evaluate",
    "frameworks",
    "health",
    "inject",
    "input_files",
    "llm_config",
    "optimizer",
    "personas",
    "platform_config",
    "projects",
    "script",
    "simulate",
    "trainset",
    "output_files",
]
