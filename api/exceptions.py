# -*- coding: utf-8 -*-
"""
向后兼容入口：保留原 `api.exceptions` 引用路径。

实际实现位于 `api.core.exceptions`，此处仅做重导出，便于渐进式重构。
"""

from api.core.exceptions import (  # noqa: F401
    EduFlowError,
    ConfigError,
    BadRequestError,
    NotFoundError,
    UnauthorizedError,
    ForbiddenError,
    ValidationError,
    PlatformAPIError,
    LLMError,
)

