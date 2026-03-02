# -*- coding: utf-8 -*-
"""CLI 平台配置：从 URL 提取课程/任务 ID，写入工作区 platform_config.json。"""
import json
import os
import sys

from api.routes.platform_config import extract_course_and_task_from_url
from api.workspace import get_workspace_dirs, get_workspace_file_path


def set_project_from_url(url: str, workspace_id: str = None):
    """从智慧树页面 URL 提取课程 ID 和训练任务 ID；若提供 workspace_id 则写入该工作区配置。"""
    print("=" * 60)
    print("从URL提取项目配置")
    print("=" * 60)
    print(f"\nURL: {url}\n")
    course_id, train_task_id = extract_course_and_task_from_url(url)
    if not course_id:
        print("[错误] 无法从URL提取课程ID")
        print("请确保URL包含 agent-course-full/<课程ID> 部分")
        sys.exit(1)
    if not train_task_id:
        print("[错误] 无法从URL提取训练任务ID")
        print("请确保URL包含 trainTaskId=<任务ID> 参数")
        sys.exit(1)
    print(f"提取到的配置:")
    print(f"  课程ID: {course_id}")
    print(f"  训练任务ID: {train_task_id}")

    if not workspace_id or not workspace_id.strip():
        print("\n[提示] 平台配置已按工作区管理，请指定工作区以写入配置：")
        print("  python main.py --set-project <URL> --workspace <工作区名>")
        print("或在前端「智慧树平台配置」中填写。")
        return

    workspace_id = workspace_id.strip()
    get_workspace_dirs(workspace_id)
    path = get_workspace_file_path(workspace_id, "platform_config.json")
    current = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                current = json.load(f)
        except Exception:
            pass
    current["course_id"] = course_id
    current["train_task_id"] = train_task_id
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    print(f"\n[成功] 已写入工作区「{workspace_id}」: {path}")
    print("\n" + "=" * 50)
    print("[重要] 还需在前端或本工作区配置中填写：")
    print("  start_node_id（SCRIPT_START）、end_node_id（SCRIPT_END）、cookie、authorization")
    print("=" * 50)
