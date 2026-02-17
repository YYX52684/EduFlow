# -*- coding: utf-8 -*-
"""CLI 平台配置：从 URL 提取并写入 .env。"""
import os
import re
import sys


def set_project_from_url(url: str):
    """从智慧树页面 URL 提取课程 ID 和训练任务 ID，并更新 .env。"""
    print("=" * 60)
    print("从URL提取项目配置")
    print("=" * 60)
    print(f"\nURL: {url}\n")
    course_match = re.search(r"agent-course-full/([^/]+)", url)
    course_id = course_match.group(1) if course_match else None
    task_match = re.search(r"trainTaskId=([^&]+)", url)
    train_task_id = task_match.group(1) if task_match else None
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
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(root, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            env_content = f.read()
        if "PLATFORM_COURSE_ID=" in env_content:
            env_content = re.sub(r"PLATFORM_COURSE_ID=.*", f"PLATFORM_COURSE_ID={course_id}", env_content)
        else:
            env_content += f"\nPLATFORM_COURSE_ID={course_id}"
        if "PLATFORM_TRAIN_TASK_ID=" in env_content:
            env_content = re.sub(r"PLATFORM_TRAIN_TASK_ID=.*", f"PLATFORM_TRAIN_TASK_ID={train_task_id}", env_content)
        else:
            env_content += f"\nPLATFORM_TRAIN_TASK_ID={train_task_id}"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)
        print(f"\n[成功] 已更新 .env 文件")
        print("\n" + "=" * 50)
        print("[重要] 还需要手动获取以下配置:")
        print("=" * 50)
        print("打开浏览器开发者工具(F12)，在Console中找到：")
        print("  1. 训练开始节点 (type: 'SCRIPT_START') 的 id")
        print("  2. 训练结束节点 (type: 'SCRIPT_END') 的 id")
        print("\n然后在 .env 中设置:")
        print("  PLATFORM_START_NODE_ID=<训练开始节点ID>")
        print("  PLATFORM_END_NODE_ID=<训练结束节点ID>")
        print("=" * 50)
    else:
        print(f"\n[警告] .env 文件不存在: {env_path}")
        print(f"请手动添加: PLATFORM_COURSE_ID={course_id}, PLATFORM_TRAIN_TASK_ID={train_task_id}")
