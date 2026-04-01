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

from api.workspace import get_project_dirs, get_workspace_file_path, WORKSPACE_ID_PATTERN
from api.exceptions import BadRequestError
from api.routes.platform_config import CFG_KEYS, extract_course_and_task_from_url

router = APIRouter()

_EDUFLOW_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WORKSPACES_DIR = os.path.join(_EDUFLOW_ROOT, "workspaces")

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
    返回 extension 工作区 LLM 配置，供插件设置模块展示。
    只存储和返回三要素：api_key / base_url / model。
    api_key 只返回安全脱敏摘要，绝不暴露前缀/后缀。
    """
    path = _extension_llm_config_path()
    raw = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            pass

    base_url = (raw.get("base_url") or "").strip().rstrip("/")
    model = (raw.get("model") or "").strip()
    api_key = (raw.get("api_key") or "").strip()

    has_key = bool(api_key)
    can_generate = bool(api_key and base_url and model)

    if has_key and base_url and model:
        mask = f"已设置（{len(api_key)} 字符）"
        config_source = "saved"
        status_message = f"就绪（{model}）"
    elif has_key:
        mask = f"已设置（{len(api_key)} 字符）"
        config_source = "saved"
        status_message = "API Key 已填，Base URL 或 Model 缺失"
    else:
        mask = ""
        config_source = "none"
        status_message = "未配置，请展开填写"

    return {
        "base_url": base_url,
        "model": model,
        "api_key_masked": mask,
        "has_api_key": has_key,
        "config_source": config_source,
        "can_generate": can_generate,
        "status_message": status_message,
        "presets": {k: {"base_url": v[0], "model": v[1]} for k, v in _LLM_PRESETS.items()},
    }


class ExtensionLLMConfigUpdate(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


@router.post("/llm/config")
def save_extension_llm_config(body: ExtensionLLMConfigUpdate):
    """
    保存 extension 工作区 LLM 配置（api_key / base_url / model 三要素）。
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
    if body.base_url is not None:
        current["base_url"] = (body.base_url or "").strip()
    if body.model is not None:
        current["model"] = (body.model or "").strip()
    current.pop("model_type", None)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    return {"message": "已保存"}


class ExtensionLLMTestRequest(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


@router.post("/llm/test")
def test_extension_llm(body: ExtensionLLMTestRequest):
    """
    测试 LLM 连通性。优先使用请求体中的参数，其次从 extension 专属配置文件读取。
    只需三要素：api_key / base_url / model。
    """
    import time
    import httpx
    from api.routes.llm_config import build_chat_completions_url

    path = _extension_llm_config_path()
    saved = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            pass

    api_key = (body.api_key or "").strip() or (saved.get("api_key") or "").strip()
    base_url = (body.base_url or "").strip().rstrip("/") or (saved.get("base_url") or "").strip().rstrip("/")
    model = (body.model or "").strip() or (saved.get("model") or "").strip()

    if not api_key:
        return {"success": False, "error_message": "缺少 API Key"}
    if not base_url:
        return {"success": False, "error_message": "缺少 Base URL"}
    if not model:
        return {"success": False, "error_message": "缺少 Model"}

    url = build_chat_completions_url(base_url)
    if not url:
        return {"success": False, "error_message": "Base URL 无效，无法构建请求地址"}

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 8,
    }

    start = time.monotonic()
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload, headers=headers)
        latency_ms = int((time.monotonic() - start) * 1000)
        if resp.status_code == 200:
            data = resp.json()
            echo = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return {
                "success": True,
                "latency_ms": latency_ms,
                "provider_echo": echo[:200],
                "error_message": None,
            }
        body_text = resp.text[:300]
        if resp.status_code == 401:
            msg = "API Key 无效或已过期"
        elif resp.status_code == 403:
            msg = "无权限访问该模型"
        elif resp.status_code == 404:
            msg = f"模型 {model} 不存在或 Base URL 有误"
        elif resp.status_code == 429:
            msg = "请求频率超限，请稍后重试"
        else:
            msg = f"HTTP {resp.status_code}: {body_text}"
        return {"success": False, "latency_ms": latency_ms, "error_message": msg}
    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"success": False, "latency_ms": latency_ms, "error_message": "请求超时（15s），请检查 Base URL 或网络"}
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"success": False, "latency_ms": latency_ms, "error_message": f"连接失败: {e}"}


@router.get("/llm/presets")
def get_extension_llm_presets():
    """返回可选模型预设列表，供插件设置模块下拉使用。"""
    return {
        "presets": [
            {"id": k, "name": k.capitalize() if k != "openai" else "OpenAI 兼容", "base_url": v[0], "model": v[1]}
            for k, v in _LLM_PRESETS.items()
        ]
    }


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


@router.get("/workspaces")
def list_workspaces_for_extension():
    """列出 workspaces 目录下子目录名，供插件选择 Web 工作区 ID。"""
    if not os.path.isdir(_WORKSPACES_DIR):
        return {"workspaces": []}
    names = []
    for name in sorted(os.listdir(_WORKSPACES_DIR)):
        path = os.path.join(_WORKSPACES_DIR, name)
        if os.path.isdir(path) and not name.startswith("."):
            names.append(name)
    return {"workspaces": names}


class ExtensionSyncPlatformRequest(BaseModel):
    """插件「一键写入 Web 端」：写入指定工作区 platform_config.json（无需 X-Workspace-Id 登录）。"""
    workspace_id: str
    url: Optional[str] = None
    cookie: Optional[str] = None
    authorization: Optional[str] = None
    start_node_id: Optional[str] = None
    end_node_id: Optional[str] = None
    base_url: Optional[str] = None
    course_id: Optional[str] = None
    train_task_id: Optional[str] = None


@router.post("/sync-platform-config")
def sync_platform_config(body: ExtensionSyncPlatformRequest):
    """
    将插件从智慧树页抓取的配置合并写入 workspaces/<workspace_id>/platform_config.json。
    与 Web 端「加载配置」逻辑一致：可从 url 提取 course_id / train_task_id。
    """
    wid = (body.workspace_id or "").strip()
    if not wid or not WORKSPACE_ID_PATTERN.match(wid):
        raise BadRequestError(
            "workspace_id 无效（允许中文、英文、数字、下划线、短横线，1~64 位）",
            details={"workspace_id": body.workspace_id},
        )
    path = get_workspace_file_path(wid, "platform_config.json")
    current: dict = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                current = json.load(f)
        except Exception:
            current = {}
    for k in CFG_KEYS:
        if k not in current:
            current[k] = ""

    if body.url and body.url.strip():
        cid, tid = extract_course_and_task_from_url(body.url.strip())
        if cid:
            current["course_id"] = cid
        if tid:
            current["train_task_id"] = tid

    if body.authorization is not None:
        current["authorization"] = (body.authorization or "").strip()
    if body.cookie is not None:
        current["cookie"] = (body.cookie or "").strip()
    if body.start_node_id is not None:
        current["start_node_id"] = (body.start_node_id or "").strip()
    if body.end_node_id is not None:
        current["end_node_id"] = (body.end_node_id or "").strip()
    if body.base_url is not None:
        current["base_url"] = (body.base_url or "").strip() or "https://cloudapi.polymas.com"
    if body.course_id is not None:
        current["course_id"] = (body.course_id or "").strip()
    if body.train_task_id is not None:
        current["train_task_id"] = (body.train_task_id or "").strip()

    if not current.get("base_url"):
        current["base_url"] = "https://cloudapi.polymas.com"

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({k: current.get(k, "") for k in CFG_KEYS}, f, ensure_ascii=False, indent=2)

    return {"message": "已写入", "workspace_id": wid}


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
        from parsers.task_extractor import extract_task_meta_from_content_structure
        from generators import ContentSplitter
        from generators.trainset_builder import write_trainset_for_document
        from simulator.student_persona import PersonaGenerator
        from api.routes.llm_config import build_chat_completions_url

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

        # 提取任务元数据（名称、描述、评价项）
        task_meta = {"task_name": "", "description": "", "evaluation_items": []}
        try:
            from parsers.docx_parser import parse_docx_with_structure
            from parsers.doc_parser import parse_doc_with_structure
            from parsers.md_parser import extract_sections
            structure = []
            if suffix == ".docx":
                _, raw_struct = parse_docx_with_structure(path)
                structure = [{"title": s["title"], "level": s.get("level", 1), "content": s.get("content", "")} for s in raw_struct]
            elif suffix == ".doc":
                _, raw_struct = parse_doc_with_structure(path)
                structure = [{"title": s["title"], "level": s.get("level", 1), "content": s.get("content", "")} for s in raw_struct]
            elif suffix == ".md":
                sections = extract_sections(full_content)
                structure = [{"title": s["title"], "level": s["level"], "content": s.get("content", "")} for s in sections]
            base_name = os.path.splitext(file.filename or "script")[0]
            task_meta = extract_task_meta_from_content_structure(full_content, structure, base_name)
        except Exception:
            pass

        stages_for_trainset = _stages_to_trainset_format(stages)
        output_dir = _extension_output_dir()
        trainset_path = write_trainset_for_document(
            output_dir,
            file.filename or "script",
            full_content,
            stages_for_trainset,
            source_file=file.filename or "",
        )

        generator = PersonaGenerator(
            {
                "api_url": build_chat_completions_url(llm.get("base_url") or ""),
                "api_key": llm.get("api_key") or "",
                "model": llm.get("model") or "",
            }
        )
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
            source_basename=f"{safe_name}_人设",
            use_level_filenames_only=False,
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
            "task_name": task_meta.get("task_name", ""),
            "description": task_meta.get("description", ""),
            "evaluation_items": task_meta.get("evaluation_items", []),
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
    evaluation_items: list | None = None
    task_name: str | None = None


@router.post("/generate-cards")
def generate_cards(req: GenerateCardsRequest):
    """
    按所选框架生成卡片 Markdown，并可附加评价项章节。
    不写文件，返回 cards_markdown 供前端展示/编辑后注入。
    """
    from generators import list_frameworks, get_framework
    from generators.evaluation_section import build_evaluation_markdown

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

    evaluation_md = build_evaluation_markdown(
        req.evaluation_items or [],
        stages,
        target_total_score=100,
        auto_generate_if_empty=True,
    )
    if evaluation_md:
        cards_content = cards_content + "\n\n---\n\n" + evaluation_md

    header = f"""# 教学卡片

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 源文件: {req.source_filename or 'API'}
> 任务名称: {req.task_name or '未命名'}
> 阶段数量: {len(stages)}

---

"""
    cards_markdown = header + cards_content
    return {"success": True, "cards_markdown": cards_markdown}


class PreviewInjectionRequest(BaseModel):
    cards_markdown: str
    task_name: str | None = None
    description: str | None = None


@router.post("/preview-injection")
def preview_injection(req: PreviewInjectionRequest):
    """
    预校验卡片 Markdown：返回标准化的 A 卡、B 卡、评价项解析结果和校验信息，
    供插件在注入前预览和确认。不实际调用平台 API。
    """
    from api_platform.card_injector import CardInjector

    if not req.cards_markdown or not req.cards_markdown.strip():
        return {"error": "cards_markdown 不能为空"}

    try:
        injector = CardInjector(api_client=None)
        all_cards = injector.parse_markdown_content(req.cards_markdown)
        a_cards, b_cards = injector.separate_cards(all_cards)
        evaluation_items = injector.parse_evaluation_items(req.cards_markdown)

        issues = injector.validate_cards(all_cards)

        a_list = []
        for c in a_cards:
            fmt = c.to_a_card_format()
            a_list.append({
                "card_id": c.card_id,
                "title": c.title,
                "step_name": fmt["step_name"],
                "interaction_rounds": fmt["interaction_rounds"],
                "has_prologue": bool(c.prologue),
            })
        b_list = [{"card_id": c.card_id, "title": c.title} for c in b_cards]

        return {
            "success": True,
            "task_name": req.task_name or "",
            "description": req.description or "",
            "total_a": len(a_cards),
            "total_b": len(b_cards),
            "a_cards": a_list,
            "b_cards": b_list,
            "evaluation_items": evaluation_items,
            "evaluation_total_score": sum(it.get("score", 0) for it in evaluation_items),
            "issues": issues,
            "summary": f"将创建 {len(a_cards)} 个节点、{max(0, len(a_cards) - 1)} 条连线"
                       + (f"、{len(evaluation_items)} 个评价项" if evaluation_items else ""),
        }
    except Exception as e:
        return {"error": f"解析失败: {e}"}


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
