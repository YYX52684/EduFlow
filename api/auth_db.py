# -*- coding: utf-8 -*-
"""
用户与工作区归属：SQLite 存储，一用户一工作区（注册时创建）。
"""
import os
import re
import secrets
import sqlite3
import time
import uuid
from typing import Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_ROOT, "data", "auth.db")

# 工作区 ID 规则：与 workspace.py 一致，用于目录名
WORKSPACE_ID_PATTERN = re.compile(r"^[\w\u4e00-\u9fff\-]{1,64}$", re.UNICODE)

# 中国大陆手机号：1 开头 11 位数字（可带 +86 或 86 前缀）
PHONE_RE = re.compile(r"^(\+?86)?1[3-9]\d{9}$")
# 邮箱简单格式
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", re.IGNORECASE)


def _row_to_dict(row: sqlite3.Row) -> dict:
    """兼容各版本：将 sqlite3.Row 转为 dict。"""
    return dict(zip(row.keys(), row))


def _get_conn() -> sqlite3.Connection:
    try:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"无法创建 data 目录: {e}") from e
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_phone_email_columns(conn: sqlite3.Connection) -> None:
    """迁移：为 users 表添加 phone、email 列（若不存在）。"""
    cur = conn.execute("PRAGMA table_info(users)")
    cols = { row[1] for row in cur.fetchall() }
    if "phone" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    if "email" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    conn.executescript("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone) WHERE phone IS NOT NULL AND phone != '';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL AND email != '';
    """)


def init_db() -> None:
    """创建表（若不存在），并执行 phone/email 迁移。"""
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workspace_owner (
                workspace_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_workspace_owner_user ON workspace_owner(user_id);
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_reset_tokens_expires ON password_reset_tokens(expires_at);
        """)
        _ensure_phone_email_columns(conn)
        conn.commit()
    finally:
        conn.close()


def _normalize_phone(raw: str) -> str:
    """手机号规范化：去空格、统一为 11 位数字（中国大陆）。"""
    s = re.sub(r"\s+", "", raw).strip()
    if s.startswith("+86"):
        s = s[3:].lstrip()
    elif s.startswith("86") and len(s) > 10:
        s = s[2:].lstrip()
    return s


def _normalize_email(raw: str) -> str:
    """邮箱规范化：去空格、小写。"""
    return (raw or "").strip().lower()


def create_user(
    password_hash: str,
    *,
    username: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
) -> tuple[str, str]:
    """
    创建用户并分配一个工作区。返回 (user_id, workspace_id)。
    phone、email、username 至少提供一个。若只提供 phone/email，会自动生成 username。
    """
    init_db()
    phone_n = _normalize_phone(phone) if phone else ""
    email_n = _normalize_email(email) if email else ""
    if not username and not phone_n and not email_n:
        raise ValueError("至少需要提供手机号、邮箱或用户名之一")
    if not username:
        if phone_n:
            username = "u" + phone_n[-4:] if len(phone_n) >= 4 else "u" + phone_n
        else:
            username = "u" + re.sub(r"[^\w]", "_", (email_n.split("@")[0] or "u")[:32])
    username = username.strip()[:64] or "user"
    # 确保 username 唯一：若与现有冲突则加后缀
    base_username = username
    user_id = str(uuid.uuid4())
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    base = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", base_username)[:64] or "user"
    workspace_id = base
    try:
        conn = _get_conn()
    except (OSError, sqlite3.OperationalError, RuntimeError) as e:
        raise RuntimeError(f"无法初始化认证数据库（请检查 data 目录权限）: {e}") from e
    try:
        n = 0
        while True:
            try:
                conn.execute(
                    """INSERT INTO users (id, username, password_hash, created_at, phone, email)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (user_id, username, password_hash, created_at, phone_n or None, email_n or None),
                )
                break
            except sqlite3.IntegrityError:
                if username == base_username and n == 0:
                    n = 1
                    username = f"{base_username}_{n}"
                else:
                    n += 1
                    username = f"{base_username}_{n}"
        n = 0
        while True:
            try:
                conn.execute(
                    "INSERT INTO workspace_owner (workspace_id, user_id) VALUES (?, ?)",
                    (workspace_id, user_id),
                )
                break
            except sqlite3.IntegrityError:
                n += 1
                workspace_id = f"{base}_{n}"
        conn.commit()
        return user_id, workspace_id
    except sqlite3.IntegrityError as e:
        raise ValueError("手机号/邮箱/用户名已存在或数据冲突") from e
    except (sqlite3.OperationalError, OSError) as e:
        raise RuntimeError(f"写入认证数据失败: {e}") from e
    finally:
        conn.close()


def get_user_by_username(username: str) -> Optional[dict]:
    """按用户名查用户，返回 dict(id, username, password_hash, phone, email) 或 None。"""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, phone, email FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_user_by_phone(phone: str) -> Optional[dict]:
    """按手机号查用户（会先规范化）。"""
    p = _normalize_phone(phone)
    if not p:
        return None
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, phone, email FROM users WHERE phone = ?",
            (p,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[dict]:
    """按邮箱查用户（会先规范化为小写）。"""
    e = _normalize_email(email)
    if not e:
        return None
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, phone, email FROM users WHERE email = ?",
            (e,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def _is_likely_phone(raw: str) -> bool:
    """规范化后是否为 11 位中国大陆手机号。"""
    p = _normalize_phone(raw)
    return len(p) == 11 and p.isdigit() and p[0] == "1" and p[1] in "3456789"


def get_user_by_identifier(identifier: str) -> Optional[dict]:
    """
    按手机号 / 邮箱 / 用户名 查用户。先尝试手机号，再邮箱，再用户名。
    返回 dict(id, username, password_hash, phone, email) 或 None。
    """
    raw = (identifier or "").strip()
    if not raw:
        return None
    if _is_likely_phone(raw):
        u = get_user_by_phone(raw)
        if u:
            return u
    e = _normalize_email(raw)
    if e and EMAIL_RE.match(raw):
        u = get_user_by_email(raw)
        if u:
            return u
    return get_user_by_username(raw)


def get_user_by_id(user_id: str) -> Optional[dict]:
    """按 id 查用户。"""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, phone, email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_workspace_owner(workspace_id: str) -> Optional[str]:
    """返回该工作区的 user_id，若未绑定则返回 None。"""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT user_id FROM workspace_owner WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()
        return row["user_id"] if row else None
    finally:
        conn.close()


def get_user_workspace(user_id: str) -> Optional[str]:
    """返回该用户绑定的 workspace_id，若没有则 None。"""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT workspace_id FROM workspace_owner WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return row["workspace_id"] if row else None
    finally:
        conn.close()


# ---------- 找回密码：重置 Token ----------
RESET_TOKEN_EXPIRE_SECONDS = 3600  # 1 小时


def create_password_reset_token(user_id: str) -> str:
    """
    为该用户创建一次性重置 Token，返回 token 字符串。
    过期时间由 RESET_TOKEN_EXPIRE_SECONDS 决定。
    """
    init_db()
    token = secrets.token_urlsafe(32)
    expires_at = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(time.time() + RESET_TOKEN_EXPIRE_SECONDS),
    )
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def get_user_id_by_reset_token(token: str) -> Optional[str]:
    """
    校验 token 存在且未过期，返回 user_id；无效或过期返回 None。
    不删除 token，由调用方在更新密码后调用 consume_reset_token。
    """
    if not token or not token.strip():
        return None
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT user_id, expires_at FROM password_reset_tokens WHERE token = ?",
            (token.strip(),),
        ).fetchone()
        if not row:
            return None
        expires_at = row["expires_at"]
        try:
            exp_ts = time.mktime(time.strptime(expires_at, "%Y-%m-%dT%H:%M:%SZ"))
        except ValueError:
            return None
        if time.time() > exp_ts:
            return None
        return row["user_id"]
    finally:
        conn.close()


def consume_reset_token(token: str) -> bool:
    """使用后删除该 token，返回是否删除成功（存在且已删为 True）。"""
    if not token or not token.strip():
        return False
    init_db()
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM password_reset_tokens WHERE token = ?",
            (token.strip(),),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_user_password(user_id: str, password_hash: str) -> None:
    """更新指定用户的密码哈希。"""
    init_db()
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )
        conn.commit()
    finally:
        conn.close()
