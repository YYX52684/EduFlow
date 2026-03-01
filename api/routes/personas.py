# -*- coding: utf-8 -*-
import os
import re
import tempfile
import yaml
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Depends
from pydantic import BaseModel

from api.routes.auth import require_workspace_owned
from api.workspace import get_project_dirs
from api.exceptions import BadRequestError
from simulator import PersonaManager, PersonaGeneratorFactory
from simulator.student_persona import PRESET_PERSONAS

router = APIRouter()

PERSONA_LIB_SUBDIR = "persona_lib"
_FS_UNSAFE = re.compile(r'[\\/:*?"<>|\s]+')


def _persona_lib_dir(workspace_id: str) -> str:
    """当前工作区 persona_lib 绝对路径。"""
    _, output_dir, _ = get_project_dirs(workspace_id)
    return os.path.join(output_dir, PERSONA_LIB_SUBDIR)


def _sanitize_persona_basename(name: str) -> str:
    """原文档名安全化，用于子目录名。"""
    name = (name or "").strip()
    name = _FS_UNSAFE.sub("_", name).strip("_")[:40]
    return name or "document"


class PersonaContentBody(BaseModel):
    persona_id: str  # 如 custom/xxx
    content: str  # YAML 正文


def _persona_to_yaml(persona) -> str:
    return yaml.dump(persona.to_dict(), allow_unicode=True, default_flow_style=False, sort_keys=False)


@router.get("/personas")
def list_personas(workspace_id: str = Depends(require_workspace_owned)):
    """列出可用人设（预设 + 工作区 persona_lib 内自定义）。"""
    manager = PersonaManager(custom_dir=_persona_lib_dir(workspace_id))
    presets = manager.list_presets()
    custom = manager.list_custom()
    return {
        "presets": presets,
        "custom": custom or [],
    }


@router.post("/personas/generate")
async def generate_personas(
    workspace_id: str = Depends(require_workspace_owned),
    num_personas: int = 3,
    file: UploadFile = File(...),
):
    """根据上传的剧本/材料生成推荐学生角色配置，写入工作区 output/persona_lib/{源文件名}_人设/。"""
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
        source_basename = os.path.splitext(file.filename or "script")[0]
        safe_name = _sanitize_persona_basename(source_basename)
        subdir = f"{safe_name}_人设"
        lib_dir = _persona_lib_dir(workspace_id)
        os.makedirs(lib_dir, exist_ok=True)
        output_dir = os.path.join(lib_dir, subdir)
        saved_paths = generator.save_personas(
            personas,
            output_dir,
            source_basename=source_basename,
            use_level_filenames_only=True,
        )
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
            "persona_dir": f"output/{PERSONA_LIB_SUBDIR}/{subdir}",
        }
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.get("/personas/content")
def get_persona_content(
    persona_id: str,
    workspace_id: str = Depends(require_workspace_owned),
):
    """获取人设 YAML 正文，供前端编辑。预设只读，自定义从工作区 persona_lib 读取。"""
    if not persona_id or not persona_id.strip():
        return {"content": "", "read_only": False}
    persona_id = persona_id.strip()
    if persona_id in PRESET_PERSONAS:
        return {
            "content": _persona_to_yaml(PRESET_PERSONAS[persona_id]),
            "read_only": True,
        }
    if persona_id.startswith("custom/"):
        name = persona_id.replace("custom/", "", 1).strip()
        if not name:
            return {"content": "", "read_only": False}
        lib = _persona_lib_dir(workspace_id)
        path = Path(lib) / f"{name}.yaml"
        lib_abs = os.path.normpath(os.path.abspath(lib))
        path_abs = os.path.normpath(os.path.abspath(path))
        if not path.exists() or not (path_abs == lib_abs or path_abs.startswith(lib_abs + os.sep)):
            return {"content": "", "read_only": False}
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content, "read_only": False}
    return {"content": "", "read_only": False}


@router.post("/personas/content")
def save_persona_content(
    body: PersonaContentBody,
    workspace_id: str = Depends(require_workspace_owned),
):
    """保存人设 YAML，仅支持自定义；路径须在工作区 persona_lib 内。"""
    persona_id = (body.persona_id or "").strip()
    if not persona_id.startswith("custom/"):
        raise BadRequestError("仅支持保存自定义人设，persona_id 须为 custom/名称")
    name = persona_id.replace("custom/", "", 1).strip()
    if not name:
        raise BadRequestError("自定义人设名称不能为空")
    lib = _persona_lib_dir(workspace_id)
    path = Path(lib) / f"{name}.yaml"
    lib_abs = os.path.normpath(os.path.abspath(lib))
    path_abs = os.path.normpath(os.path.abspath(path))
    if not (path_abs == lib_abs or path_abs.startswith(lib_abs + os.sep)):
        raise BadRequestError("路径不在 persona_lib 内")
    try:
        data = yaml.safe_load(body.content or "")
        if not isinstance(data, dict):
            raise BadRequestError("YAML 须为键值结构")
        from simulator.student_persona import StudentPersona
        StudentPersona.from_dict(data)
    except BadRequestError:
        raise
    except Exception as e:
        raise BadRequestError(f"人设格式有误: {e}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body.content or "")
    return {"saved": persona_id}


class DeletePersonaRequest(BaseModel):
    persona_id: str  # 如 custom/xxx_人设/优秀 或 custom/xxx_人设（删整目录）


@router.delete("/personas")
def delete_persona(
    body: DeletePersonaRequest,
    workspace_id: str = Depends(require_workspace_owned),
):
    """删除工作区 persona_lib 内的人设文件或整个人设目录（custom/xxx_人设）。"""
    persona_id = (body.persona_id or "").strip()
    if not persona_id.startswith("custom/"):
        raise BadRequestError("仅支持删除自定义人设，persona_id 须为 custom/...")
    name = persona_id.replace("custom/", "", 1).strip()
    if not name:
        raise BadRequestError("persona_id 不能为空")
    lib = _persona_lib_dir(workspace_id)
    path = Path(lib) / name
    lib_abs = os.path.normpath(os.path.abspath(lib))
    path_abs = os.path.normpath(os.path.abspath(path))
    if not (path_abs == lib_abs or path_abs.startswith(lib_abs + os.sep)):
        raise BadRequestError("路径不在 persona_lib 内")
    if path.is_dir():
        import shutil
        shutil.rmtree(path, ignore_errors=True)
        return {"deleted": persona_id}
    if path.is_file():
        path.unlink()
        return {"deleted": persona_id}
    path_yaml = path.with_suffix(".yaml") if path.suffix != ".yaml" else path
    if path_yaml.is_file():
        path_yaml.unlink()
        return {"deleted": persona_id}
    from api.exceptions import NotFoundError
    raise NotFoundError("人设文件或目录不存在", details={"persona_id": persona_id})
