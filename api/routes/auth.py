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
    EMAIL_RE,
    _normalize_email,
    _normalize_phone,
    consume_reset_token,
    create_password_reset_token,
    create_user,
    get_user_by_id,
    get_user_by_identifier,
    get_user_by_username,
    get_user_workspace,
    get_user_id_by_reset_token,
    get_workspace_owner,
    update_user_password,
)
from api.exceptions import BadRequestError, ForbiddenError, UnauthorizedError, ValidationError
from api.mail_sender import send_password_reset_email
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
    """手机号、邮箱至少填其一；用户名可选（不填则自动生成）。"""
    phone: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    password: str


class LoginBody(BaseModel):
    """identifier 为手机号、邮箱或用户名。"""
    identifier: str
    password: str


class ForgotPasswordBody(BaseModel):
    """手机号或邮箱。"""
    identifier: str


class ResetPasswordBody(BaseModel):
    token: str
    new_password: str


class AdminSetPasswordBody(BaseModel):
    """开发环境临时使用：直接按 identifier 重置密码。"""
    identifier: str
    new_password: str

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


def _check_phone_format(phone: str) -> None:
    p = _normalize_phone(phone)
    if not p or len(p) != 11 or not p.isdigit() or p[0] != "1" or p[1] not in "3456789":
        raise ValidationError("请输入正确的中国大陆手机号（11 位）")


def _check_email_format(email: str) -> None:
    e = _normalize_email(email)
    if not e or not EMAIL_RE.match(e):
        raise ValidationError("请输入正确的邮箱地址")


@router.post("/register")
def register(body: RegisterBody):
    """注册：手机号或邮箱至少填其一，创建用户并分配工作区，返回 token 与 workspace_id。"""
    phone = (body.phone or "").strip() or None
    email = (body.email or "").strip() or None
    username = (body.username or "").strip() or None
    password = body.password or ""
    if not phone and not email and not username:
        raise ValidationError("请填写手机号、邮箱或用户名至少一项")
    if phone:
        _check_phone_format(phone)
        if get_user_by_identifier(phone):
            raise BadRequestError("该手机号已被注册")
    if email:
        _check_email_format(email)
        if get_user_by_identifier(email):
            raise BadRequestError("该邮箱已被注册")
    if username:
        if not _username_ok(username):
            raise ValidationError("用户名仅允许字母、数字、中文、._-，且不超过 64 字符")
        if get_user_by_username(username):
            raise BadRequestError("用户名已被使用")
    if len(password) < 6:
        raise ValidationError("密码至少 6 位")
    password_hash = pwd_ctx.hash(password)
    try:
        user_id, workspace_id = create_user(
            password_hash, username=username or None, phone=phone, email=email
        )
    except ValueError as e:
        raise BadRequestError(str(e))
    except RuntimeError as e:
        raise BadRequestError("无法创建用户，请检查服务器 data 目录是否可写。")
    user = get_user_by_id(user_id)
    display_name = (user.get("username") or user.get("phone") or user.get("email") or user_id)[:64]
    token = _issue_token(user_id, display_name)
    return {
        "token": token,
        "user": {"id": user_id, "username": display_name},
        "workspace_id": workspace_id,
    }


@router.post("/login")
def login(body: LoginBody):
    """登录：手机号 / 邮箱 / 用户名 + 密码，返回 token 与 workspace_id。"""
    identifier = (body.identifier or "").strip()
    password = body.password or ""
    if not identifier or not password:
        raise ValidationError("请输入手机号/邮箱/用户名和密码")
    user = get_user_by_identifier(identifier)
    if not user or not pwd_ctx.verify(password, user["password_hash"]):
        raise UnauthorizedError("手机号/邮箱/用户名或密码错误")
    workspace_id = get_user_workspace(user["id"])
    display_name = (user.get("username") or user.get("phone") or user.get("email") or user["id"])[:64]
    token = _issue_token(user["id"], display_name)
    return {
        "token": token,
        "user": {"id": user["id"], "username": display_name},
        "workspace_id": workspace_id or "",
    }


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordBody):
    """
    申请找回密码：输入手机号或邮箱。若用户存在则生成重置链接。
    为防枚举用户，无论是否存在均返回相同提示；未配置邮件时在响应中返回 reset_url（仅开发/内网）。
    """
    identifier = (body.identifier or "").strip()
    if not identifier:
        raise ValidationError("请输入手机号或邮箱")
    user = get_user_by_identifier(identifier)
    out: dict = {"message": "若该账号存在，您将收到重置链接。请查收邮件或短信或联系管理员。"}
    if user:
        token = create_password_reset_token(user["id"])
        base_url = os.getenv("EDUFLOW_PUBLIC_URL", "").strip() or os.getenv("BASE_URL", "").strip()
        # 使用查询参数形式，便于前端通过 location.search 解析：/?reset_token=...
        reset_path = "/?reset_token=" + token
        reset_url = (base_url.rstrip("/") + reset_path) if base_url else None
        to_email = (user.get("email") or "").strip()
        if to_email and reset_url:
            sent = send_password_reset_email(to_email, reset_url)
            if sent:
                out["message"] = "若该账号存在，重置链接已发送至您的邮箱，请查收。"
        if not (to_email and reset_url and out.get("message", "").find("已发送") >= 0):
            if reset_url:
                out["reset_url"] = reset_url
            else:
                out["reset_token"] = token
                out["message"] = "若该账号存在，请使用下方链接重置密码（请勿泄露）。"
    return out


@router.post("/reset-password")
def reset_password(body: ResetPasswordBody):
    """使用重置 Token 设置新密码。Token 一次性有效，使用后作废。"""
    token = (body.token or "").strip()
    new_password = body.new_password or ""
    if not token:
        raise ValidationError("缺少重置链接或链接已失效")
    if len(new_password) < 6:
        raise ValidationError("新密码至少 6 位")
    user_id = get_user_id_by_reset_token(token)
    if not user_id:
        raise BadRequestError("重置链接无效或已过期，请重新申请找回密码")
    password_hash = pwd_ctx.hash(new_password)
    update_user_password(user_id, password_hash)
    consume_reset_token(token)
    return {"message": "密码已重置，请使用新密码登录"}


@router.post("/admin-set-password")
def admin_set_password(body: AdminSetPasswordBody):
    """
    开发环境临时接口：通过手机号 / 邮箱 / 用户名直接重置密码。
    仅当 EDUFLOW_ENV != production 时可用，生产环境会直接拒绝。
    """
    if os.getenv("EDUFLOW_ENV", "").strip().lower() == "production":
        raise ForbiddenError("生产环境禁用该接口")
    identifier = (body.identifier or "").strip()
    new_password = body.new_password or ""
    if not identifier or not new_password:
        raise ValidationError("请输入账号和新密码")
    if len(new_password) < 6:
        raise ValidationError("新密码至少 6 位")
    user = get_user_by_identifier(identifier)
    if not user:
        raise BadRequestError("用户不存在")
    password_hash = pwd_ctx.hash(new_password)
    update_user_password(user["id"], password_hash)
    return {"message": "密码已重置（开发环境）"}


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
