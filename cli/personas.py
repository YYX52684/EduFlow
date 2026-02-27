# -*- coding: utf-8 -*-
"""CLI 人设：列出人设、根据材料生成推荐角色。"""
import os
import sys

from cli.common import get_parser_for_file


def generate_personas(
    input_path: str,
    num_personas: int = 3,
    output_dir: str = None,
    verbose: bool = False,
):
    """根据原始教学材料生成推荐的学生角色配置。"""
    from simulator import PersonaGeneratorFactory

    print("=" * 60)
    print("智能角色生成器")
    print("=" * 60)
    print(f"\n输入文件: {input_path}")
    print(f"生成数量: {num_personas}\n")
    if not os.path.exists(input_path):
        print(f"[错误] 文件不存在: {input_path}")
        sys.exit(1)
    try:
        file_parser = get_parser_for_file(input_path)
        content = file_parser(input_path)
        print(f"[OK] 已读取文件，内容长度: {len(content)} 字符")
    except ValueError:
        with open(input_path, "r", encoding="utf-8") as f:
            content = f.read()
        print(f"[OK] 已读取文本文件，内容长度: {len(content)} 字符")
    print("\n[生成] 正在调用 LLM 生成角色配置...")
    generator = PersonaGeneratorFactory.create_from_env()
    try:
        personas = generator.generate_from_material(
            material_content=content,
            num_personas=num_personas,
            include_preset_types=True,
        )
        print(f"\n[OK] 成功生成 {len(personas)} 个角色配置")
        print("\n" + "-" * 40)
        print("生成的角色概览:")
        print("-" * 40)
        for i, persona in enumerate(personas, 1):
            print(f"\n【角色 {i}】{persona.name}")
            print(f"  背景: {persona.background[:50]}..." if len(persona.background) > 50 else f"  背景: {persona.background}")
            print(f"  性格: {persona.personality}")
            print(f"  目标: {persona.goal[:50]}..." if len(persona.goal) > 50 else f"  目标: {persona.goal}")
            print(f"  参与度: {persona.engagement_level}")
            if verbose:
                print(f"  优势: {', '.join(persona.strengths[:3])}")
                print(f"  不足: {', '.join(persona.weaknesses[:2])}")
        source_basename = os.path.splitext(os.path.basename(input_path))[0]
        saved_paths = generator.save_personas(personas, output_dir, source_basename=source_basename)
        print("\n" + "-" * 40)
        print("已保存角色配置文件:")
        print("-" * 40)
        for path in saved_paths:
            print(f"  - {path}")
        print("\n" + "=" * 60)
        print("[完成] 角色生成成功!")
        print("\n使用方法:")
        for path in saved_paths:
            filename = os.path.basename(path)
            print(f"  python main.py --simulate <cards.md> --persona \"custom/{filename}\"")
        print("=" * 60)
    except Exception as e:
        print(f"\n[错误] 角色生成失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def list_personas():
    """列出可用的人设。"""
    from simulator import PersonaManager

    print("=" * 60)
    print("可用人设列表")
    print("=" * 60)
    manager = PersonaManager()
    print("\n【预设人设】")
    for name in manager.list_presets():
        print(f"  - {name}")
    print("\n【自定义人设】")
    custom = manager.list_custom()
    if custom:
        for name in custom:
            print(f"  - custom/{name}")
    else:
        print("  (暂无)")
    print("\n使用方法:")
    print("  --persona excellent        # 使用预设人设")
    print("  --persona custom/xxx.yaml  # 使用自定义人设")
    print("  --generate-personas <input_file>  # 根据材料生成推荐人设")
