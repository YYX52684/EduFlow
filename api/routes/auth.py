# -*- coding: utf-8 -*-
"""
用户认证：注册、登录、当前用户。JWT 放在 Authorization: Bearer <token> 或 cookie。
"""
import os
import time
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from passlib.context import CryptContext
from pydantic import BaseModel

from api.auth_db import (
    create_user,
    get_user_by_id,
    get_user_by_username,
    get_user_workspace,
    get_workspace_owner,
)
from api.exceptions import BadRequestError, ForbiddenError, UnauthorizedError, ValidationError
from api.workspace import get_workspace_id

# 使用 Argon2，无长度限制，且不受 bcrypt 72 字节 / passlib 自检影响
pwd_ctx = CryptContext(schemes=["argon2"], deprecated="auto")

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# JWT 密钥：生产环境（EDUFLOW_ENV=production）必须设置 JWT_SECRET 且不能使用默认值，否则拒绝启动
_JWT_DEFAULT = "eduflow-dev-secret-change-in-production"
_RAW_JWT = os.getenv("JWT_SECRET")
JWT_SECRET = _RAW_JWT if (_RAW_JWT and _RAW_JWT.strip()) else _JWT_DEFAULT
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

_is_production = os.getenv("EDUFLOW_ENV", "").strip().lower() == "production"
if _is_production:
    if not _RAW_JWT or not _RAW_JWT.strip() or JWT_SECRET == _JWT_DEFAULT:
        raise RuntimeError(
            "生产环境必须设置 JWT_SECRET，且不能使用默认值。请在 .env 中配置：JWT_SECRET=<随机长字符串>。"
        )
elif JWT_SECRET == _JWT_DEFAULT:
    import logging
    logging.getLogger(__name__).warning(
        "JWT_SECRET 未配置，当前使用默认值，仅适合开发。生产环境请设置 EDUFLOW_ENV=production 并在 .env 中配置 JWT_SECRET。"
    )


class RegisterBody(BaseModel):
    username: str
    password: str


class LoginBody(BaseModel):
    username: str
    password: str


def _username_ok(s: str) -> bool:
    if not s or len(s) > 64:
        return False
    for c in s:
        if c.isalnum() or c in "._-":
            continue
        if "\u4e00" <= c <= "\u9fff":
            continue
        return False
    return True


def _issue_token(user_id: str, username: str) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "exp": int(time.time()) + JWT_EXPIRE_DAYS * 86400,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except Exception:
        return None


def get_token_from_request(request: Request) -> Optional[str]:
    """从 Authorization: Bearer <token> 或 cookie eduflow_token 取 token。"""
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:].strip()
    return request.cookies.get("eduflow_token")


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """
    依赖：解析 JWT，返回当前用户 { id, username }。
    未登录或 token 无效则抛出 UnauthorizedError。
    """
    token = get_token_from_request(request)
    if not token:
        raise UnauthorizedError("请先登录")
    payload = _decode_token(token)
    if not payload or not payload.get("sub"):
        raise UnauthorizedError("登录已过期，请重新登录")
    user = get_user_by_id(payload["sub"])
    if not user:
        raise UnauthorizedError("用户不存在，请重新登录")
    return {"id": user["id"], "username": user["username"]}


@router.post("/register")
def register(body: RegisterBody):
    """注册：创建用户并分配工作区，返回 token 与 workspace_id。"""
    username = (body.username or "").strip()
    password = body.password or ""
    if not username:
        raise ValidationError("用户名不能为空")
    if not _username_ok(username):
        raise ValidationError("用户名仅允许字母、数字、中文、._-，且不超过 64 字符")
    if len(password) < 6:
        raise ValidationError("密码至少 6 位")
    if get_user_by_username(username):
        raise BadRequestError("用户名已被使用")
    password_hash = pwd_ctx.hash(password)
    try:
        user_id, workspace_id = create_user(username, password_hash)
    except ValueError as e:
        raise BadRequestError(str(e))
    except RuntimeError as e:
        raise BadRequestError("无法创建用户，请检查服务器 data 目录是否可写。")
    token = _issue_token(user_id, username)
    return {
        "token": token,
        "user": {"id": user_id, "username": username},
        "workspace_id": workspace_id,
    }


@router.post("/login")
def login(body: LoginBody):
    """登录：校验用户名密码，返回 token 与 workspace_id。"""
    username = (body.username or "").strip()
    password = body.password or ""
    if not username or not password:
        raise ValidationError("请输入用户名和密码")
    user = get_user_by_username(username)
    if not user or not pwd_ctx.verify(password, user["password_hash"]):
        raise UnauthorizedError("用户名或密码错误")
    workspace_id = get_user_workspace(user["id"])
    token = _issue_token(user["id"], user["username"])
    return {
        "token": token,
        "user": {"id": user["id"], "username": user["username"]},
        "workspace_id": workspace_id or "",
    }


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    """当前用户信息及绑定的工作区。"""
    workspace_id = get_user_workspace(current_user["id"])
    return {
        "user": current_user,
        "workspace_id": workspace_id or "",
    }


def require_workspace_owned(
    workspace_id: str = Depends(get_workspace_id),
    current_user: dict = Depends(get_current_user),
) -> str:
    """依赖：仅当当前用户拥有该工作区时返回 workspace_id，否则 403。"""
    owner = get_workspace_owner(workspace_id)
    if owner != current_user["id"]:
        raise ForbiddenError("无权限访问该工作区")
    return workspace_id
