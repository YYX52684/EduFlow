# -*- coding: utf-8 -*-
from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel
from simulator import PersonaManager, PersonaGeneratorFactory
from simulator.student_persona import PRESET_PERSONAS
import os
import tempfile
import yaml

router = APIRouter()


class PersonaContentBody(BaseModel):
    persona_id: str  # 如 custom/xxx
    content: str  # YAML 正文


def _persona_to_yaml(persona) -> str:
    return yaml.dump(persona.to_dict(), allow_unicode=True, default_flow_style=False, sort_keys=False)


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
        if suffix in (".docx", ".doc", ".pdf"):
            from parsers import parse_docx, parse_doc, parse_pdf
            if suffix == ".docx":
                text = parse_docx(tmp_path)
            elif suffix == ".doc":
                text = parse_doc(tmp_path)
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


@router.get("/personas/content")
def get_persona_content(persona_id: str):
    """获取人设 YAML 正文，供前端编辑。预设返回序列化后的 YAML，自定义从文件读取。"""
    if not persona_id or not persona_id.strip():
        return {"content": "", "read_only": False}
    persona_id = persona_id.strip()
    # 预设
    if persona_id in PRESET_PERSONAS:
        return {
            "content": _persona_to_yaml(PRESET_PERSONAS[persona_id]),
            "read_only": True,
        }
    # 自定义 custom/name
    if persona_id.startswith("custom/"):
        name = persona_id.replace("custom/", "", 1).strip()
        if not name:
            return {"content": "", "read_only": False}
        manager = PersonaManager()
        path = manager.custom_dir / f"{name}.yaml"
        if not path.exists():
            return {"content": "", "read_only": False}
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content, "read_only": False}
    return {"content": "", "read_only": False}


@router.post("/personas/content")
def save_persona_content(body: PersonaContentBody):
    """保存人设 YAML，仅支持自定义（persona_id 须为 custom/name）。"""
    persona_id = (body.persona_id or "").strip()
    if not persona_id.startswith("custom/"):
        from fastapi import HTTPException
        raise HTTPException(400, "仅支持保存自定义人设，persona_id 须为 custom/名称")
    name = persona_id.replace("custom/", "", 1).strip()
    if not name:
        from fastapi import HTTPException
        raise HTTPException(400, "自定义人设名称不能为空")
    manager = PersonaManager()
    manager.custom_dir.mkdir(parents=True, exist_ok=True)
    path = manager.custom_dir / f"{name}.yaml"
    try:
        # 校验 YAML 可被解析为人设
        data = yaml.safe_load(body.content or "")
        if not isinstance(data, dict):
            from fastapi import HTTPException
            raise HTTPException(400, "YAML 须为键值结构")
        from simulator.student_persona import StudentPersona
        StudentPersona.from_dict(data)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(400, f"人设格式有误: {e}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body.content or "")
    return {"saved": persona_id}
