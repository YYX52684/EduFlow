# -*- coding: utf-8 -*-
"""
API 层统一业务异常
便于前端/调用方区分错误类型，并映射为 HTTP 状态码与统一 JSON 体。
"""
from typing import Any, Optional


class EduFlowError(Exception):
    """EduFlow 业务异常基类"""

    def __init__(
        self,
        message: str,
        code: str = "ERROR",
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": True,
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class ConfigError(EduFlowError):
    """配置缺失或非法（如未配置 API Key、工作区 ID 缺失）"""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="CONFIG_ERROR", status_code=400, details=details)


class BadRequestError(EduFlowError):
    """请求错误（如缺少必要头、参数非法、路径超出工作区）"""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="BAD_REQUEST", status_code=400, details=details)


class NotFoundError(EduFlowError):
    """资源不存在（如文件、工作区、卡片文件）"""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="NOT_FOUND", status_code=404, details=details)


class ValidationError(EduFlowError):
    """请求参数或业务数据校验失败"""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="VALIDATION_ERROR", status_code=422, details=details)


class PlatformAPIError(EduFlowError):
    """智慧树平台 API 调用失败（网络/鉴权/业务错误）"""

    def __init__(self, message: str, status_code: int = 502, details: Optional[dict] = None):
        super().__init__(message, code="PLATFORM_API_ERROR", status_code=status_code, details=details)


class LLMError(EduFlowError):
    """LLM 调用失败（超时、限流、返回格式异常）"""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, code="LLM_ERROR", status_code=502, details=details)
