"""
能力训练文档生成编排：LM 初始化、DSPy 调用、校验重试。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import dspy

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    DOUBAO_API_KEY,
    DOUBAO_BASE_URL,
    DOUBAO_MODEL,
    DEFAULT_MODEL_TYPE,
    MAX_TOKENS,
    TEMPERATURE,
    TRAINING_DOC_CONFIG,
)
from .dspy_card_runtime import invoke_with_lm, run_in_generation_context
from .dspy_training_doc_helpers import (
    normalize_training_doc_markdown,
    validate_training_doc_markdown,
)
from .dspy_training_doc_modules import TrainingDocGeneratorModule


class TrainingDocGenerator:
    """根据教学材料生成标准能力训练文档（Markdown）。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_type: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.model_type = (model_type or DEFAULT_MODEL_TYPE).lower()
        self.base_url = (base_url or "").strip()
        self.model = (model or "").strip()

        if self.base_url and self.model:
            self.api_key = api_key or DOUBAO_API_KEY or DEEPSEEK_API_KEY
        elif self.model_type == "doubao":
            self.api_key = api_key or DOUBAO_API_KEY
        else:
            self.api_key = api_key or DEEPSEEK_API_KEY
        if not self.api_key:
            raise ValueError("未提供API密钥，请在 Web 设置中填写或设置 .env")

        self.lm = self._create_lm()
        self._module = TrainingDocGeneratorModule()

    def _create_lm(self, api_key_override: Optional[str] = None) -> dspy.LM:
        key = api_key_override or self.api_key
        if self.base_url and self.model:
            return dspy.LM(
                model=f"openai/{self.model}",
                api_key=key,
                api_base=self.base_url,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
            )
        if self.model_type == "doubao":
            key = key or DOUBAO_API_KEY
            return dspy.LM(
                model=f"openai/{DOUBAO_MODEL}",
                api_key=key,
                api_base=DOUBAO_BASE_URL,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
            )
        key = key or DEEPSEEK_API_KEY
        return dspy.LM(
            model=f"openai/{DEEPSEEK_MODEL}",
            api_key=key,
            api_base=DEEPSEEK_BASE_URL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )

    def _retry_hint(self, errors: List[str]) -> str:
        return (
            "【上次输出未通过校验，请完整重写文档】\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\n请严格满足全部要求后再输出 Markdown。"
        )

    def _generate_impl(
        self,
        course_name: str,
        training_theme: str,
        source_material: str,
        image_context: str,
        extra_instruction: str = "",
    ) -> str:
        override = None
        if not (self.base_url and self.model):
            override = DEEPSEEK_API_KEY if self.model_type != "doubao" else DOUBAO_API_KEY
        self.lm = self._create_lm(api_key_override=override)

        material = source_material.strip()
        if extra_instruction:
            material = f"{extra_instruction}\n\n---\n\n{material}"

        result = invoke_with_lm(
            self.lm,
            self._module,
            course_name=course_name.strip(),
            training_theme=training_theme.strip(),
            source_material=material,
            image_context=(image_context or "").strip() or "（暂无）",
        )
        return normalize_training_doc_markdown(str(getattr(result, "document_markdown", "") or ""))

    def generate_training_document(
        self,
        course_name: str,
        training_theme: str,
        source_material: str,
        image_context: str = "",
    ) -> Tuple[str, List[str]]:
        """
        生成并校验文档。

        Returns:
            (markdown, validation_errors) — 若校验失败仍返回最后一次生成文本，errors 非空。
        """
        max_retries = int(TRAINING_DOC_CONFIG.get("max_validation_retries", 2))
        extra = ""
        last_text = ""
        last_errors: List[str] = []

        for attempt in range(max_retries + 1):
            last_text = self._generate_impl(
                course_name,
                training_theme,
                source_material,
                image_context,
                extra_instruction=extra,
            )
            ok, last_errors = validate_training_doc_markdown(last_text)
            if ok:
                return last_text, []
            if attempt < max_retries:
                extra = self._retry_hint(last_errors)

        return last_text, last_errors

    def generate_training_document_blocking(
        self,
        course_name: str,
        training_theme: str,
        source_material: str,
        image_context: str = "",
    ) -> str:
        """与卡片生成一致：非主线程时切到专用 DSPy 线程。"""

        def _task():
            text, errors = self.generate_training_document(
                course_name, training_theme, source_material, image_context
            )
            if errors:
                note = "\n\n<!-- training_doc_validation: " + "; ".join(errors) + " -->\n"
                return text + note
            return text

        return run_in_generation_context(_task)
