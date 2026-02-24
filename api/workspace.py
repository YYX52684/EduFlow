# -*- coding: utf-8 -*-
"""
工作区隔离：按 X-Workspace-Id 区分用户，input/output 互不影响。
支持当前项目（课程/小项目）切换，路径可解析到项目子目录。
"""
import json
import os
import re
from typing import Optional

from fastapi import Header

from api.exceptions import BadRequestError, NotFoundError

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WORKSPACES_DIR = os.path.join(_ROOT, "workspaces")
_CURRENT_PROJECT_FILE = "current_project.json"

# 项目名（工作区标识）：可读名称，用于 URL 与目录。禁止路径相关字符。
# 允许：中文、英文、数字、下划线、短横线；1~64 字符
WORKSPACE_ID_PATTERN = re.compile(r"^[\w\u4e00-\u9fff\-]{1,64}$", re.UNICODE)

# 用于拼接目录时做安全替换：Windows 非法文件名字符
_FS_UNSAFE = re.compile(r'[\\/:*?"<>|]')


def _sanitize_workspace_dir(name: str) -> str:
    """将项目名中不可做目录名的字符替换为下划线，避免跨平台问题。"""
    return _FS_UNSAFE.sub("_", name).strip() or "default"


def _decode_workspace_id_header(value: Optional[str]) -> str:
    """解码请求头：前端可能对中文等非 ASCII 做 Base64 编码（HTTP 头仅允许 ISO-8859-1）。"""
    if not value or not value.strip():
        return (value or "").strip()
    import base64
    s = value.strip()
    try:
        if re.match(r"^[A-Za-z0-9+/]+=*$", s) and len(s) % 4 in (0, 2, 3):
            decoded = base64.b64decode(s).decode("utf-8")
            if decoded:
                return decoded
    except Exception:
        pass
    return s


def get_workspace_id(x_workspace_id: str | None = Header(None, alias="X-Workspace-Id")) -> str:
    """从请求头获取并校验项目名（工作区标识），缺失或非法则 BadRequestError。"""
    if not x_workspace_id or not x_workspace_id.strip():
        raise BadRequestError(
            "缺少请求头 X-Workspace-Id。请从带 /w/项目名 的地址进入（如 /w/编译原理）。"
        )
    wid = _decode_workspace_id_header(x_workspace_id)
    if not wid or not WORKSPACE_ID_PATTERN.match(wid):
        raise BadRequestError(
            "X-Workspace-Id 格式非法（允许中文、英文、数字、下划线、短横线，1~64 位，且不能含 / \\ 等路径字符）"
        )
    return wid


def get_workspace_dirs(workspace_id: str) -> tuple[str, str, str]:
    """返回 (input_dir, output_dir, workspace_root)。目录不存在则创建。"""
    dir_name = _sanitize_workspace_dir(workspace_id)
    workspace_root = os.path.join(_WORKSPACES_DIR, dir_name)
    input_dir = os.path.join(workspace_root, "input")
    output_dir = os.path.join(workspace_root, "output")
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    return input_dir, output_dir, workspace_root


def get_workspace_file_path(workspace_id: str, filename: str) -> str:
    """返回工作区根目录下某文件的绝对路径。filename 仅文件名（如 llm_config.json），不含子路径。"""
    _, _, workspace_root = get_workspace_dirs(workspace_id)
    if os.path.isabs(filename) or ".." in filename or filename.strip() != filename:
        raise BadRequestError("filename 须为工作区根目录下的文件名", details={"filename": filename})
    return os.path.join(workspace_root, filename)


def safe_relative(path: str, base: str) -> Optional[str]:
    """返回 path 相对 base 的路径（正斜杠），若 path 不在 base 下则返回 None。"""
    try:
        r = os.path.relpath(path, base)
        if r.startswith("..") or os.path.isabs(r):
            return None
        return r.replace("\\", "/")
    except Exception:
        return None


def list_dir_files(
    root_dir: str,
    path_prefix: str,
    allowed_ext: Optional[set] = None,
) -> list:
    """
    递归列出 root_dir 下文件，返回 [{"path": path_prefix+rel, "name": name}, ...]。
    allowed_ext 为 None 时不过滤扩展名；否则只保留扩展名在 allowed_ext 中的文件。
    """
    if not os.path.isdir(root_dir):
        return []
    out = []
    for root, _, names in os.walk(root_dir):
        for name in sorted(names) if allowed_ext is None else names:
            ext = os.path.splitext(name)[1].lower()
            if allowed_ext is not None and ext not in allowed_ext:
                continue
            full = os.path.join(root, name)
            rel = safe_relative(full, root_dir)
            if rel:
                out.append({"path": path_prefix + rel.replace("\\", "/"), "name": name})
    out.sort(key=lambda x: x["path"])
    return out


def list_dir_files_with_mtime(
    root_dir: str,
    path_prefix: str,
    allowed_ext: Optional[set] = None,
) -> list:
    """
    递归列出 root_dir 下文件，返回 [{"path", "name", "mtime"}, ...]。
    mtime 为修改时间戳（秒，用于按时间排序）。
    """
    if not os.path.isdir(root_dir):
        return []
    out = []
    for root, _, names in os.walk(root_dir):
        for name in sorted(names) if allowed_ext is None else names:
            ext = os.path.splitext(name)[1].lower()
            if allowed_ext is not None and ext not in allowed_ext:
                continue
            full = os.path.join(root, name)
            rel = safe_relative(full, root_dir)
            if rel:
                try:
                    mtime = os.path.getmtime(full)
                except OSError:
                    mtime = 0
                out.append({
                    "path": path_prefix + rel.replace("\\", "/"),
                    "name": name,
                    "mtime": int(mtime),
                })
    out.sort(key=lambda x: x["path"])
    return out


def save_upload_to_dir(
    root_dir: str,
    content: bytes,
    filename: str,
    subpath: str,
    allowed_ext: set,
    path_prefix: str,
    save_as: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    将上传内容写入 root_dir 下 subpath（可为空）。返回 (path_prefix+rel, None) 成功，
    (None, error_msg) 表示扩展名不允许等错误。
    save_as 非空时用其 basename 作为保存文件名。
    """
    name = (filename or "file").strip() or "file"
    name = os.path.basename(name)
    if save_as and str(save_as).strip():
        name = os.path.basename(str(save_as).strip())
    ext = os.path.splitext(name)[1].lower()
    if ext not in allowed_ext:
        return (None, f"仅支持 {', '.join(sorted(allowed_ext))} 格式")
    subpath = (subpath or "").strip().replace("\\", "/").strip("/")
    if path_prefix and subpath.startswith(path_prefix):
        subpath = subpath[len(path_prefix) :].strip("/")
    target_dir = os.path.join(root_dir, subpath) if subpath else root_dir
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, name)
    with open(target_path, "wb") as f:
        f.write(content)
    rel = safe_relative(target_path, root_dir) or name
    return (path_prefix + rel.replace("\\", "/"), None)


def _safe_relative_path(part: str) -> bool:
    """校验为安全相对路径成分（无 .. 且非空）。"""
    if not part or part.strip() != part:
        return False
    if ".." in part or os.path.isabs(part):
        return False
    return True


def get_current_project(workspace_id: str) -> Optional[dict]:
    """读取当前项目配置。返回 None 或 {"course": str, "project": str}。"""
    input_dir, _, workspace_root = get_workspace_dirs(workspace_id)
    path = os.path.join(workspace_root, _CURRENT_PROJECT_FILE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        course = (data.get("course") or "").strip()
        project = (data.get("project") or "").strip()
        if not course or not _safe_relative_path(course):
            return None
        if not _safe_relative_path(project):
            project = ""
        return {"course": course, "project": project}
    except Exception:
        return None


def set_current_project(workspace_id: str, course: str, project: str = "") -> None:
    """设置当前项目。course 为课程目录名，project 为子项目目录名（可为空表示整课）。"""
    course = (course or "").strip()
    project = (project or "").strip()
    if not _safe_relative_path(course) or (project and not _safe_relative_path(project)):
        raise BadRequestError("course/project 含非法路径")
    get_workspace_dirs(workspace_id)
    dir_name = _sanitize_workspace_dir(workspace_id)
    workspace_root = os.path.join(_WORKSPACES_DIR, dir_name)
    path = os.path.join(workspace_root, _CURRENT_PROJECT_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"course": course, "project": project}, f, ensure_ascii=False, indent=2)


def list_projects(workspace_id: str) -> list[dict]:
    """
    列出所有项目：课程为 input 下子目录，小项目为课程下子目录。
    若课程下无子目录，则课程本身视为一个项目（project 名为 course 名）。
    返回 [{"course": str, "project": str, "path": str}, ...]，path 为相对 input 的路径。
    """
    input_dir, _, _ = get_workspace_dirs(workspace_id)
    result = []
    if not os.path.isdir(input_dir):
        return result
    for course in sorted(os.listdir(input_dir)):
        course_path = os.path.join(input_dir, course)
        if not os.path.isdir(course_path) or not _safe_relative_path(course):
            continue
        subdirs = [d for d in os.listdir(course_path) if os.path.isdir(os.path.join(course_path, d)) and _safe_relative_path(d)]
        if subdirs:
            for proj in sorted(subdirs):
                result.append({
                    "course": course,
                    "project": proj,
                    "path": f"{course}/{proj}",
                })
        else:
            result.append({"course": course, "project": "", "path": course})
    return result


def get_project_dirs(workspace_id: str) -> tuple[str, str, str]:
    """
    若已设置当前项目，返回 (project_input_dir, project_output_dir, workspace_root)；
    否则与 get_workspace_dirs 一致，返回 (input_dir, output_dir, workspace_root)。
    """
    input_dir, output_dir, workspace_root = get_workspace_dirs(workspace_id)
    current = get_current_project(workspace_id)
    if not current:
        return input_dir, output_dir, workspace_root
    course = current["course"]
    project = (current["project"] or "").strip()
    if project:
        pin = os.path.normpath(os.path.join(input_dir, course, project))
        pout = os.path.normpath(os.path.join(output_dir, course, project))
    else:
        pin = os.path.normpath(os.path.join(input_dir, course))
        pout = os.path.normpath(os.path.join(output_dir, course))
    base_in = os.path.normpath(input_dir)
    base_out = os.path.normpath(output_dir)
    if not (pin == base_in or pin.startswith(base_in + os.sep)) or not (pout == base_out or pout.startswith(base_out + os.sep)):
        raise BadRequestError("当前项目路径非法")
    os.makedirs(pin, exist_ok=True)
    os.makedirs(pout, exist_ok=True)
    return pin, pout, workspace_root


def normalize_output_rel(path: str) -> str:
    """将 path 规范化为带 output/ 前缀的相对路径（正斜杠）。"""
    rel = path.strip().replace("\\", "/").lstrip("/")
    if not rel.startswith("output/"):
        rel = "output/" + rel
    return rel


def resolve_workspace_path(
    workspace_id: str,
    relative_path: str,
    kind: str = "output",
    must_exist: bool = False,
) -> str:
    """
    将相对路径（如 output/xxx.md 或 xxx.md）解析为工作区内的绝对路径。
    若 must_exist=True 且路径不存在，抛出 NotFoundError。
    """
    project_input, project_output, _ = get_project_dirs(workspace_id)
    base = project_output if kind == "output" else project_input
    path = relative_path.strip().replace("\\", "/").lstrip("/")
    if path.startswith("input/"):
        path = path[6:]
        base = project_input
    elif path.startswith("output/"):
        path = path[7:]
        base = project_output
    full = os.path.normpath(os.path.join(base, path))
    base_abs = os.path.normpath(base)
    if not (full == base_abs or full.startswith(base_abs + os.sep)):
        raise BadRequestError("路径不能超出工作区", details={"path": relative_path})
    if must_exist and not os.path.exists(full):
        raise NotFoundError("文件或目录不存在", details={"path": relative_path, "kind": kind})
    return full


def resolve_input_path(
    workspace_id: str,
    relative_path: str,
    must_exist: bool = False,
) -> str:
    """
    将相对路径解析为工作区 input 下的绝对路径。
    若 relative_path 为 "input" 或空，返回当前项目的 input 目录；
    否则自动补 "input/" 前缀后解析。
    """
    path = relative_path.strip().replace("\\", "/").lstrip("/")
    if path in ("", "input", "input/"):
        return get_project_dirs(workspace_id)[0]
    if not path.startswith("input/"):
        path = "input/" + path
    return resolve_workspace_path(workspace_id, path, kind="input", must_exist=must_exist)


def resolve_output_path(
    workspace_id: str,
    relative_path: str,
    must_exist: bool = False,
) -> str:
    """
    将相对路径解析为工作区 output 下的绝对路径。
    自动补 "output/" 前缀后解析。
    """
    path = relative_path.strip().replace("\\", "/").lstrip("/")
    if not path.startswith("output/"):
        path = "output/" + path
    return resolve_workspace_path(workspace_id, path, kind="output", must_exist=must_exist)
