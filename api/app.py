# -*- coding: utf-8 -*-
"""
EduFlow Web API 入口
不修改 main.py，仅复用现有模块提供 REST 接口。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routes import health, frameworks, personas, script, cards, simulate, evaluate, inject, platform_config, input_files, output_files, trainset, optimizer, projects, llm_config

app = FastAPI(
    title="EduFlow API",
    description="教学卡片生成与模拟测试 Web 接口",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
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
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(llm_config.router, prefix="/api/llm", tags=["llm"])

web_dir = os.path.join(_ROOT, "web", "static")
index_path = os.path.join(web_dir, "index.html")


def _serve_index():
    if os.path.isfile(index_path):
        return FileResponse(index_path)
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
