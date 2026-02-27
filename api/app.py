# -*- coding: utf-8 -*-
"""
EduFlow Web API 入口
不修改 main.py，仅复用现有模块提供 REST 接口。
"""
import io
import logging
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Windows 下强制 stdout/stderr 使用 UTF-8，避免优化器/仿真等输出 Unicode 字符时触发 GBK 编码错误
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .routes import (
    health,
    frameworks,
    personas,
    script,
    cards,
    simulate,
    evaluate,
    inject,
    platform_config,
    input_files,
    output_files,
    trainset,
    optimizer,
    closed_loop,
    projects,
    llm_config,
    auth,
    extension,
)
from .exceptions import EduFlowError
from .middleware import RequestIDMiddleware, get_request_id

logger = logging.getLogger(__name__)

app = FastAPI(
    title="EduFlow API",
    description="教学卡片生成与模拟测试 Web 接口",
    version="0.1.0",
)

# 先挂载 request_id 中间件，便于异常处理中写入 request_id
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(EduFlowError)
def eduflow_error_handler(request: Request, exc: EduFlowError):
    """业务异常 → 统一 JSON 错误体，并带上 request_id。

    兼顾两类调用方：
    - 新前端 / 集成方：读取 success=false 与 error.{code,message,details};
    - 旧前端 / 现有测试：继续使用顶层 error/code/message 字段。
    """
    request_id = get_request_id(request)
    logger.warning(
        "request_error request_id=%s path=%s method=%s code=%s message=%s",
        request_id,
        request.url.path,
        request.method,
        exc.code,
        exc.message,
    )
    base = exc.to_dict()
    envelope = {
        "success": False,
        "error_detail": {
            "code": base.get("code", "ERROR"),
            "message": base.get("message", ""),
            "details": base.get("details", {}),
        },
        "request_id": request_id,
    }
    # 兼容旧字段：error/code/message/details 继续保留在顶层
    envelope.update(base)
    return JSONResponse(status_code=exc.status_code, content=envelope)


@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception):
    """未捕获异常 → 500 + 统一格式，避免泄露堆栈；响应头带 request_id。"""
    request_id = get_request_id(request)
    logger.exception(
        "unhandled_exception request_id=%s path=%s method=%s error=%s",
        request_id,
        request.url.path,
        request.method,
        str(exc),
    )
    body = {
        "success": False,
        "error_detail": {
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误，请稍后重试。",
            "details": {},
        },
        "error": True,
        "code": "INTERNAL_ERROR",
        "message": "服务器内部错误，请稍后重试。",
        "details": {},
        "request_id": request_id,
    }
    return JSONResponse(status_code=500, content=body)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(frameworks.router, prefix="/api", tags=["frameworks"])
app.include_router(personas.router, prefix="/api", tags=["personas"])
app.include_router(script.router, prefix="/api/script", tags=["script"])
app.include_router(cards.router, prefix="/api/cards", tags=["cards"])
app.include_router(simulate.router, prefix="/api/simulate", tags=["simulate"])
app.include_router(evaluate.router, prefix="/api", tags=["evaluate"])
app.include_router(inject.router, prefix="/api/inject", tags=["inject"])
app.include_router(platform_config.router, prefix="/api/platform", tags=["platform"])
app.include_router(input_files.router, prefix="/api/input", tags=["input"])
app.include_router(output_files.router, prefix="/api/output", tags=["output"])
app.include_router(trainset.router, prefix="/api/trainset", tags=["trainset"])
app.include_router(optimizer.router, prefix="/api/optimizer", tags=["optimizer"])
app.include_router(closed_loop.router, prefix="/api/closed-loop", tags=["closed-loop"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(llm_config.router, prefix="/api/llm", tags=["llm"])
app.include_router(extension.router, prefix="/api/extension", tags=["extension"])

web_dir = os.path.join(_ROOT, "web", "static")
legacy_index_path = os.path.join(web_dir, "index.html")

frontend_dist_dir = os.path.join(_ROOT, "frontend", "dist")
spa_index_path = os.path.join(frontend_dist_dir, "index.html")


def _serve_index():
    """根据是否已构建新前端，优先返回 React SPA 的 index.html。"""
    if os.path.isfile(spa_index_path):
        return FileResponse(spa_index_path)
    if os.path.isfile(legacy_index_path):
        return FileResponse(legacy_index_path)
    return {"message": "EduFlow API", "docs": "/docs"}


@app.get("/")
def index():
    return _serve_index()


@app.get("/w/{rest:path}")
def workspace_page(rest: str):
    """SPA 工作区路由，始终返回首页由前端解析 /w/<workspace_id>。"""
    return _serve_index()


if os.path.isdir(web_dir):
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

# 若已构建新的 React SPA，挂载其静态资源目录（Vite 默认输出到 frontend/dist）
if os.path.isdir(frontend_dist_dir):
    assets_dir = os.path.join(frontend_dist_dir, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

