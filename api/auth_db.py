# -*- coding: utf-8 -*-
"""
用户与工作区归属：SQLite 存储，一用户一工作区（注册时创建）。
"""
import os
import re
import sqlite3
import uuid
from typing import Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_ROOT, "data", "auth.db")

# 工作区 ID 规则：与 workspace.py 一致，用于目录名
WORKSPACE_ID_PATTERN = re.compile(r"^[\w\u4e00-\u9fff\-]{1,64}$", re.UNICODE)


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


def init_db() -> None:
    """创建表（若不存在）。"""
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
        """)
        conn.commit()
    finally:
        conn.close()


def create_user(username: str, password_hash: str) -> tuple[str, str]:
    """
    创建用户并分配一个工作区。返回 (user_id, workspace_id)。
    workspace_id 由 username 生成（合法字符），若冲突则加后缀。
    """
    init_db()
    user_id = str(uuid.uuid4())
    import time
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # 工作区名：仅保留允许的字符，限制长度
    base = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", username.strip())[:64] or "user"
    workspace_id = base
    try:
        conn = _get_conn()
    except (OSError, sqlite3.OperationalError, RuntimeError) as e:
        raise RuntimeError(f"无法初始化认证数据库（请检查 data 目录权限）: {e}") from e
    try:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username.strip(), password_hash, created_at),
        )
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
        raise ValueError("用户名已存在或数据冲突") from e
    except (sqlite3.OperationalError, OSError) as e:
        raise RuntimeError(f"写入认证数据失败: {e}") from e
    finally:
        conn.close()


def get_user_by_username(username: str) -> Optional[dict]:
    """按用户名查用户，返回 dict(id, username, password_hash) 或 None。"""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: str) -> Optional[dict]:
    """按 id 查用户。"""
    init_db()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE id = ?",
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
