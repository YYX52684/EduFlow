# -*- coding: utf-8 -*-
"""
API 统一异常与 request_id 中间件测试。
"""
import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.exceptions import (
    EduFlowError,
    ConfigError,
    NotFoundError,
    ValidationError,
)


def test_eduflow_error_to_dict():
    """EduFlowError.to_dict 包含 error/code/message/details。"""
    err = ConfigError("未配置 API Key", details={"key": "api_key"})
    d = err.to_dict()
    assert d["error"] is True
    assert d["code"] == "CONFIG_ERROR"
    assert d["message"] == "未配置 API Key"
    assert d["details"] == {"key": "api_key"}


def test_not_found_status_code():
    """NotFoundError 映射为 404。"""
    err = NotFoundError("文件不存在")
    assert err.status_code == 404


def test_exception_handler_returns_json_with_request_id():
    """健康检查正常且响应头带 X-Request-Id。"""
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert "X-Request-Id" in resp.headers
    assert len(resp.headers["X-Request-Id"]) > 0


def test_missing_workspace_returns_unified_error_body():
    """缺少 X-Workspace-Id 时返回统一错误体（error/code/message/request_id）。"""
    client = TestClient(app)
    resp = client.get("/api/simulate/cards-parsed", params={"path": "output/any.md"})
    assert resp.status_code == 400
    data = resp.json()
    assert data.get("error") is True
    assert "code" in data
    assert "message" in data
    assert "request_id" in data
