# -*- coding: utf-8 -*-
"""
Chrome 插件专用 API：上传文件 → 解析 → 分幕 → 生成卡片，返回 Markdown。
无需 workspace 认证，使用默认 LLM 配置（.env 或 extension 工作区）。
"""
import os
import tempfile
from datetime import datetime

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

router = APIRouter()

EXTENSION_WORKSPACE = "extension"


def _get_llm_config():
    """获取 extension 使用的 LLM 配置"""
    from api.routes.llm_config import get_llm_config
    return get_llm_config(EXTENSION_WORKSPACE)


@router.post("/upload-and-generate")
async def upload_and_generate(file: UploadFile = File(...)):
    """
    上传剧本文件，解析内容、分幕、生成卡片，返回 cards_markdown。
    供 Chrome 插件调用，使用默认 LLM 配置。
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
        from config import CARD_GENERATOR_TYPE

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
        framework_id = "dspy" if any(m["id"] == "dspy" for m in frameworks) else (CARD_GENERATOR_TYPE or "default")
        if not any(m["id"] == framework_id for m in frameworks):
            framework_id = frameworks[0]["id"] if frameworks else "default"

        GeneratorClass, _ = get_framework(framework_id)
        if framework_id == "dspy":
            generator = GeneratorClass(
                api_key=llm.get("api_key"),
                model_type=llm.get("model_type"),
                base_url=llm.get("base_url") or None,
                model=llm.get("model") or None,
            )
        else:
            generator = GeneratorClass(
                api_key=llm.get("api_key"),
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
