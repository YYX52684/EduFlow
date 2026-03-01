# -*- coding: utf-8 -*-
"""
Chrome 插件专用 API：六步流程（上传解析、框架、人设、评分、生成卡片、注入）。
无需 workspace 认证，使用 extension 工作区与默认 LLM 配置。
插件用户可在侧边栏「API 与模型」中填写 API Key，保存至 extension 工作区。
"""
import os
import json
import re
import tempfile
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from api.workspace import get_project_dirs, get_workspace_file_path
from api.exceptions import BadRequestError

router = APIRouter()

EXTENSION_WORKSPACE = "extension"
PERSONA_LIB_SUBDIR = "persona_lib"
LLM_CONFIG_FILE = "llm_config.json"
_FS_UNSAFE = re.compile(r'[\\/:*?"<>|\s]+')

# 与 api.routes.llm_config 一致，供 extension 读写配置
_LLM_PRESETS = {
    "deepseek": ("https://api.deepseek.com", "deepseek-chat"),
    "doubao": ("https://llm-service.polymas.com/api/openai/v1", "Doubao-1.5-pro-32k"),
    "openai": ("https://api.openai.com/v1", "gpt-4o"),
}


def _get_llm_config():
    """获取 extension 使用的 LLM 配置。"""
    from api.routes.llm_config import get_llm_config
    return get_llm_config(EXTENSION_WORKSPACE)


def _extension_llm_config_path() -> str:
    """Extension 工作区 llm_config.json 路径。"""
    return get_workspace_file_path(EXTENSION_WORKSPACE, LLM_CONFIG_FILE)


@router.get("/llm/config")
def get_extension_llm_config():
    """
    返回 extension 工作区 LLM 配置，供插件侧边栏展示。
    api_key 脱敏返回；未配置时 has_api_key 为 false，提示用户在侧边栏填写。
    """
    path = _extension_llm_config_path()
    raw = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            pass
    llm = _get_llm_config()
    model_type = (llm.get("model_type") or "doubao").strip().lower()
    if model_type not in _LLM_PRESETS:
        model_type = "doubao"
    base_url = (llm.get("base_url") or "").rstrip("/") or _LLM_PRESETS[model_type][0]
    model = (llm.get("model") or "").strip() or _LLM_PRESETS[model_type][1]
    api_key = (llm.get("api_key") or "").strip()
    raw_key = (raw.get("api_key") or "").strip()
    if api_key:
        mask = (api_key[:8] + "…" + api_key[-4:]) if len(api_key) > 12 else "已设置"
    else:
        mask = ""
    return {
        "model_type": model_type,
        "base_url": base_url,
        "model": model,
        "api_key_masked": mask,
        "has_api_key": bool(api_key),
    }


class ExtensionLLMConfigUpdate(BaseModel):
    api_key: Optional[str] = None
    model_type: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


@router.post("/llm/config")
def save_extension_llm_config(body: ExtensionLLMConfigUpdate):
    """
    保存 extension 工作区 LLM 配置（API Key、模型等）。
    供插件侧边栏「API 与模型」保存，无需登录。
    """
    path = _extension_llm_config_path()
    current = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                current = json.load(f)
        except Exception:
            pass
    if body.api_key is not None:
        current["api_key"] = (body.api_key or "").strip()
    if body.model_type is not None:
        t = (body.model_type or "doubao").strip().lower()
        current["model_type"] = t if t in _LLM_PRESETS else "doubao"
    if body.base_url is not None:
        current["base_url"] = (body.base_url or "").strip()
    if body.model is not None:
        current["model"] = (body.model or "").strip()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    return {"message": "已保存，解析与生成将使用该 API Key 与模型"}


def _extension_output_dir() -> str:
    """Extension 工作区 output 目录。"""
    _, output_dir, _ = get_project_dirs(EXTENSION_WORKSPACE)
    return output_dir


def _extension_persona_lib_dir() -> str:
    """Extension 工作区 persona_lib 绝对路径。"""
    output_dir = _extension_output_dir()
    return os.path.join(output_dir, PERSONA_LIB_SUBDIR)


def _sanitize_persona_basename(name: str) -> str:
    """原文档名安全化，用于人设子目录名。"""
    name = (name or "").strip()
    name = _FS_UNSAFE.sub("_", name).strip("_")[:40]
    return name or "document"


def _stages_to_trainset_format(stages: list) -> list:
    """将 ContentSplitter 的 stages 转为 trainset 所需格式。保留 interaction_rounds 供卡片生成使用。"""
    return [
        {
            "id": s.get("id"),
            "title": s.get("title"),
            "description": s.get("description"),
            "role": s.get("role"),
            "task": s.get("task"),
            "key_points": s.get("key_points", []),
            "content_excerpt": s.get("content_excerpt") or "",
            "interaction_rounds": s.get("interaction_rounds"),
        }
        for s in stages
    ]


@router.post("/upload-parse")
async def upload_parse(file: UploadFile = File(...)):
    """
    上传剧本文件，解析、分幕、写入 trainset、生成并写入人设。
    返回 stages、full_content、trainset_path、personas 等供后续步骤使用。
    """
    suffix = (os.path.splitext(file.filename or "")[1] or ".md").lower()
    if suffix not in (".md", ".docx", ".doc", ".pdf"):
        return {"error": "仅支持 .md / .docx / .doc / .pdf"}

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        path = tmp.name

    try:
        from parsers import get_parser_for_extension
        from generators import ContentSplitter
        from generators.trainset_builder import write_trainset_for_document
        from simulator import PersonaGeneratorFactory

        full_content = get_parser_for_extension(suffix)(path)
        llm = _get_llm_config()
        splitter = ContentSplitter(
            api_key=llm.get("api_key") or None,
            base_url=llm.get("base_url") or None,
            model=llm.get("model") or None,
        )
        result = splitter.analyze(full_content)
        stages = result.get("stages", [])
        if not stages:
            return {"error": "未能分析出有效阶段，请检查剧本内容"}

        stages_for_trainset = _stages_to_trainset_format(stages)
        output_dir = _extension_output_dir()
        trainset_path = write_trainset_for_document(
            output_dir,
            file.filename or "script",
            full_content,
            stages_for_trainset,
            source_file=file.filename or "",
        )

        generator = PersonaGeneratorFactory.create_from_env()
        personas = generator.generate_from_material(
            material_content=full_content,
            num_personas=3,
            include_preset_types=True,
        )
        source_basename = os.path.splitext(file.filename or "script")[0]
        safe_name = _sanitize_persona_basename(source_basename)
        subdir = f"{safe_name}_人设"
        lib_dir = _extension_persona_lib_dir()
        os.makedirs(lib_dir, exist_ok=True)
        persona_output_dir = os.path.join(lib_dir, subdir)
        generator.save_personas(
            personas,
            output_dir=persona_output_dir,
            source_basename=source_basename,
            use_level_filenames_only=True,
        )

        persona_dir = f"output/{PERSONA_LIB_SUBDIR}/{subdir}"
        level_names = ["优秀", "一般", "较差"]
        persona_list = [
            {
                "id": f"custom/{subdir}/{level_names[i]}",
                "name": getattr(p, "name", level_names[i]),
            }
            for i, p in enumerate(personas[:3])
        ]

        return {
            "success": True,
            "filename": file.filename,
            "stages": stages_for_trainset,
            "full_content": full_content,
            "trainset_path": trainset_path,
            "personas": persona_list,
            "persona_dir": persona_dir,
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


@router.get("/frameworks")
def get_frameworks():
    """列出所有可用的卡片生成框架（id / name / description）。"""
    from generators import list_frameworks
    items = list_frameworks() or []
    frameworks = [
        {"id": m["id"], "name": m.get("name", m["id"]), "description": m.get("description", "")}
        for m in items
    ]
    return {"frameworks": frameworks}


@router.get("/personas")
def list_personas():
    """列出 extension 工作区可用人设（预设 + persona_lib 自定义）。"""
    from simulator import PersonaManager
    lib_dir = _extension_persona_lib_dir()
    manager = PersonaManager(custom_dir=lib_dir)
    presets = manager.list_presets()
    custom = manager.list_custom()
    return {"presets": presets, "custom": custom or []}


def _persona_to_yaml(persona) -> str:
    return yaml.dump(persona.to_dict(), allow_unicode=True, default_flow_style=False, sort_keys=False)


@router.get("/personas/content")
def get_persona_content(persona_id: str):
    """获取人设 YAML 正文。预设只读，自定义可编辑。"""
    from simulator.student_persona import PRESET_PERSONAS
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
        lib = _extension_persona_lib_dir()
        path = Path(lib) / f"{name}.yaml"
        lib_abs = os.path.normpath(os.path.abspath(lib))
        path_abs = os.path.normpath(os.path.abspath(path))
        if not path.exists() or not (path_abs == lib_abs or path_abs.startswith(lib_abs + os.sep)):
            return {"content": "", "read_only": False}
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content, "read_only": False}
    return {"content": "", "read_only": False}


class PersonaContentBody(BaseModel):
    persona_id: str
    content: str


@router.post("/personas/content")
def save_persona_content(body: PersonaContentBody):
    """保存人设 YAML，仅支持自定义（custom/...）。"""
    persona_id = (body.persona_id or "").strip()
    if not persona_id.startswith("custom/"):
        raise BadRequestError("仅支持保存自定义人设，persona_id 须为 custom/名称")
    name = persona_id.replace("custom/", "", 1).strip()
    if not name:
        raise BadRequestError("自定义人设名称不能为空")
    lib = _extension_persona_lib_dir()
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


class GenerateCardsRequest(BaseModel):
    framework_id: str
    stages: list
    full_content: str
    source_filename: str | None = None
    scoring_system_id: str | None = None


@router.post("/generate-cards")
def generate_cards(req: GenerateCardsRequest):
    """
    按所选框架生成卡片 Markdown。scoring_system_id 暂不参与逻辑，仅占位。
    不写文件，返回 cards_markdown 供前端展示/编辑后注入。
    """
    from generators import list_frameworks, get_framework
    stages = req.stages
    if not stages:
        return {"error": "stages 不能为空"}
    frameworks = list_frameworks() or []
    framework_id = req.framework_id or "dspy"
    if not any(m["id"] == framework_id for m in frameworks):
        framework_id = frameworks[0]["id"] if frameworks else "dspy"
    try:
        GeneratorClass, _ = get_framework(framework_id)
    except ValueError as e:
        return {"error": str(e)}
    llm = _get_llm_config()
    generator = GeneratorClass(
        api_key=llm.get("api_key"),
        model_type=llm.get("model_type"),
        base_url=llm.get("base_url") or None,
        model=llm.get("model") or None,
    )
    cards_content = generator.generate_all_cards(stages, req.full_content)
    header = f"""# 教学卡片

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 源文件: {req.source_filename or 'API'}
> 阶段数量: {len(stages)}

---

"""
    cards_markdown = header + cards_content
    return {"success": True, "cards_markdown": cards_markdown}


@router.post("/upload-and-generate")
async def upload_and_generate(file: UploadFile = File(...)):
    """
    兼容旧版：上传剧本后一次性解析并生成卡片。
    新流程请使用分步 API：upload-parse → generate-cards。
    """
    suffix = (os.path.splitext(file.filename or "")[1] or ".md").lower()
    if suffix not in (".md", ".docx", ".doc", ".pdf"):
        return {"error": "仅支持 .md / .docx / .doc / .pdf"}

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        path = tmp.name

    try:
        from parsers import get_parser_for_extension
        from generators import ContentSplitter, list_frameworks, get_framework

        full_content = get_parser_for_extension(suffix)(path)
        llm = _get_llm_config()
        splitter = ContentSplitter(
            api_key=llm.get("api_key") or None,
            base_url=llm.get("base_url") or None,
            model=llm.get("model") or None,
        )
        result = splitter.analyze(full_content)
        stages = result.get("stages", [])
        if not stages:
            return {"error": "未能分析出有效阶段，请检查剧本内容"}

        frameworks = list_frameworks()
        framework_id = "dspy"
        if not any(m["id"] == framework_id for m in (frameworks or [])):
            framework_id = frameworks[0]["id"] if frameworks else "dspy"

        GeneratorClass, _ = get_framework(framework_id)
        generator = GeneratorClass(
            api_key=llm.get("api_key"),
            model_type=llm.get("model_type"),
            base_url=llm.get("base_url") or None,
            model=llm.get("model") or None,
        )
        cards_content = generator.generate_all_cards(stages, full_content)

        header = f"""# 教学卡片

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 源文件: {file.filename or 'API'}
> 阶段数量: {len(stages)}

---

"""
        cards_markdown = header + cards_content

        return {
            "success": True,
            "stages": stages,
            "full_content": full_content,
            "cards_markdown": cards_markdown,
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass
