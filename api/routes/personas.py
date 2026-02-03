# -*- coding: utf-8 -*-
from fastapi import APIRouter, UploadFile, File
from simulator import PersonaManager, PersonaGeneratorFactory
import os
import tempfile

router = APIRouter()


@router.get("/personas")
def list_personas():
    """列出可用人设（预设 + 自定义）"""
    manager = PersonaManager()
    presets = manager.list_presets()
    custom = manager.list_custom()
    return {
        "presets": presets,
        "custom": [f"custom/{name}" for name in (custom or [])],
    }


@router.post("/personas/generate")
async def generate_personas(
    num_personas: int = 3,
    file: UploadFile = File(...),
):
    """根据上传的剧本/材料生成推荐学生角色配置。"""
    suffix = os.path.splitext(file.filename or "")[1].lower() or ".txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        if suffix in (".docx", ".pdf"):
            from parsers import parse_docx, parse_pdf
            if suffix == ".docx":
                text = parse_docx(tmp_path)
            else:
                text = parse_pdf(tmp_path)
        generator = PersonaGeneratorFactory.create_from_env()
        personas = generator.generate_from_material(
            material_content=text,
            num_personas=num_personas,
            include_preset_types=True,
        )
        saved_paths = generator.save_personas(personas, None)
        return {
            "count": len(personas),
            "personas": [
                {
                    "name": p.name,
                    "background": p.background,
                    "personality": p.personality,
                    "goal": p.goal,
                    "engagement_level": p.engagement_level,
                }
                for p in personas
            ],
            "saved_paths": saved_paths or [],
        }
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
