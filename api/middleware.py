# -*- coding: utf-8 -*-
"""
请求中间件：注入 request_id，便于日志与问题排查。
"""
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


REQUEST_ID_HEADER = "X-Request-Id"
REQUEST_ID_STATE_KEY = "request_id"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求生成或透传 request_id，并写入响应头。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def get_request_id(request: Request) -> str:
    """从当前请求获取 request_id（需在 RequestIDMiddleware 之后使用）。"""
    return getattr(request.state, REQUEST_ID_STATE_KEY, "") or ""
