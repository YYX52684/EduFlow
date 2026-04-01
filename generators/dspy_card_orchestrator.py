"""
DSPy 卡片生成编排器。

负责模型初始化、A/B 卡生成编排、覆盖补强重试、结尾卡拼装与多线程执行策略。
"""

from typing import List, Optional

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
)
from . import dspy_card_helpers as card_helpers
from .dspy_card_modules import (
    CardAGeneratorModule,
    CardAEndingGeneratorModule,
    CardBGeneratorModule,
)
from .dspy_card_runtime import invoke_with_lm, run_in_generation_context
from .dspy_utils import Retryable, format_card_section, reset_positive_feedback_history


class DSPyCardGenerator:
    """基于 DSPy 的卡片生成器。"""

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
        self.card_a_generator = CardAGeneratorModule()
        self.card_a_ending_generator = CardAEndingGeneratorModule()
        self.card_b_generator = CardBGeneratorModule()

    def _create_lm(self, api_key_override: Optional[str] = None) -> dspy.LM:
        """创建 LM 实例。支持 doubao / deepseek / 自定义 base_url+model。"""
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

    def _create_stage_meta(self, stage: dict, default_interaction_rounds: int = 5) -> str:
        """兼容旧调用：创建阶段元数据块。"""
        return card_helpers.create_stage_meta(stage, default_interaction_rounds)

    def _build_stage_coverage_hints(self, stage: dict) -> List[str]:
        """兼容旧调用：抽取本幕需要覆盖的原文锚点。"""
        return card_helpers.build_stage_coverage_hints(stage)

    def _calc_missing_anchors(self, result: dspy.Prediction, coverage_hints: List[str]) -> List[str]:
        """兼容旧调用：计算 A 卡中未显式覆盖的锚点。"""
        return card_helpers.calc_missing_anchors(result, coverage_hints)

    def _build_display_constraints(self, raw_constraints: str, stage: dict) -> str:
        """兼容旧调用：构建 A 卡展示层约束。"""
        return card_helpers.build_display_constraints(raw_constraints, stage)

    def _build_b_display_constraints(self, use_narrator: bool) -> str:
        """兼容旧调用：构建 B 卡展示层约束。"""
        return card_helpers.build_b_display_constraints(use_narrator)

    def _build_ending_display_constraints(self) -> str:
        """兼容旧调用：构建结尾卡展示层约束。"""
        return card_helpers.build_ending_display_constraints()

    def _format_card_a(self, result: dspy.Prediction, stage_index: int, stage_meta: str, stage: dict) -> str:
        """兼容旧调用：格式化 A 类卡片输出。"""
        return card_helpers.format_card_a(result, stage_index, stage_meta, stage)

    def _format_card_b(
        self,
        result: dspy.Prediction,
        stage_index: int,
        total_stages: int,
        stage: Optional[dict] = None,
    ) -> str:
        """兼容旧调用：格式化 B 类卡片输出。"""
        return card_helpers.format_card_b(result, stage=stage)

    def _invoke_with_lm(self, module, **kwargs):
        """统一串行化 dspy.configure 与模块调用。"""
        return invoke_with_lm(self.lm, module, **kwargs)

    def _build_card_a_excerpt(self, stage: dict, stage_index: int) -> tuple[str, List[str]]:
        """构建 A 卡输入的 content_excerpt，并返回覆盖锚点。"""
        content_excerpt = stage.get("content_excerpt", "")
        coverage_hints = self._build_stage_coverage_hints(stage)
        if coverage_hints:
            must_cover_text = "、".join(coverage_hints[:10])
            content_excerpt = (
                "【分幕全覆盖要求】所有A卡合起来必须覆盖完整文档。你负责第"
                f"{stage_index}幕，必须尽量覆盖本幕 content_excerpt/key_points 的核心信息，"
                "不得只给抽象总结。\n"
                f"【本幕必覆盖锚点】{must_cover_text}\n\n"
                f"{content_excerpt}"
            )

        return content_excerpt, coverage_hints

    def _build_anchor_retry_excerpt(self, content_excerpt: str, missing: List[str]) -> str:
        """生成覆盖补强重试时的增强版 excerpt。"""
        return (
            "【覆盖补强重试】上一版输出仍有锚点遗漏。请在 Role/Context/Interaction/Transition 中"
            "明确纳入以下遗漏锚点，避免泛化表达。\n"
            f"【遗漏锚点】{'、'.join(missing[:10])}\n\n"
            f"{content_excerpt}"
        )

    def _generate_ending_card_a(self, stages: List[dict], original_content: str) -> str:
        """
        在所有卡片之后追加一张结尾用 A 类卡片：
        - 卡片ID为 卡片{N+1}A（N=总阶段数），确保排序时位于最后
        - 轮次固定为 0
        - 说完则结束整个流程
        """
        last_stage = stages[-1] if stages else {}
        npc_role_raw = str(last_stage.get("role", "") or "")
        npc_role = card_helpers.sanitize_npc_role_text(npc_role_raw)

        base_title = str(last_stage.get("title") or "").strip()
        if base_title:
            ending_title = f"{base_title}（收尾）"
        elif npc_role:
            ending_title = f"{npc_role}（收尾）"
        else:
            ending_title = "结尾收尾卡片"

        base_desc = str(last_stage.get("description") or last_stage.get("task") or "").strip()
        if base_desc:
            ending_desc = (
                f"围绕「{base_title or npc_role or '本次实训'}」场景做自然收尾，"
                "用于结束本次剧情的A类卡片，轮次为0，说完则结束整个流程。"
            )
        else:
            ending_desc = "用于结束剧情的A类卡片，轮次为0，说完则结束整个流程。"

        ending_stage_meta = self._create_stage_meta(
            {
                "title": ending_title,
                "description": ending_desc,
                "interaction_rounds": 0,
            },
            default_interaction_rounds=0,
        )

        ending_result = self._invoke_with_lm(
            self.card_a_ending_generator,
            full_script=original_content,
            last_stage_title=str(last_stage.get("title", "") or ""),
            last_stage_role=npc_role,
            last_stage_goal=str(last_stage.get("task", "") or ""),
            last_stage_key_points=", ".join(last_stage.get("key_points", [])),
            last_stage_excerpt=str(last_stage.get("content_excerpt", "") or ""),
        )

        constraints = self._build_ending_display_constraints()
        sections = [
            ending_stage_meta,
            format_card_section("Role", ending_result.role_section),
            format_card_section("Context", ending_result.context_section),
            format_card_section("Interaction", ending_result.interaction_section),
            format_card_section("Transition", ending_result.transition_section),
            format_card_section("Constraints", constraints),
        ]

        if '"interaction_rounds": 0' not in ending_stage_meta:
            ending_stage_meta = self._create_stage_meta(
                {
                    "title": ending_title,
                    "description": ending_desc,
                    "interaction_rounds": 0,
                },
                default_interaction_rounds=0,
            )
            sections[0] = ending_stage_meta

        card_body = "\n\n".join(sections)
        ending_num = len(stages) + 1
        return f"# 卡片{ending_num}A\n\n{card_body}"

    @Retryable(max_retries=3, exceptions=(Exception,))
    def generate_card_a(
        self,
        stage: dict,
        stage_index: int,
        total_stages: int,
        full_script: str,
    ) -> str:
        """生成 A 类卡片（NPC 角色卡片）。"""
        include_prologue = stage_index == 1
        strategy = card_helpers.detect_interaction_strategy(stage)
        is_guidance = strategy == "guidance"
        content_excerpt, coverage_hints = self._build_card_a_excerpt(stage, stage_index)
        stage_key_points_text = ", ".join(stage.get("key_points", []))
        npc_role = card_helpers.sanitize_npc_role_text(stage.get("role", "") or "")

        result = self._invoke_with_lm(
            self.card_a_generator,
            full_script=full_script,
            stage_title=stage.get("title", ""),
            npc_role=npc_role,
            scene_goal=stage.get("task", ""),
            key_points=stage_key_points_text,
            content_excerpt=content_excerpt,
            is_guidance=is_guidance,
            include_prologue=include_prologue,
        )

        missing = self._calc_missing_anchors(result, coverage_hints) if coverage_hints else []
        if missing:
            retry_excerpt = self._build_anchor_retry_excerpt(content_excerpt, missing)
            result = self._invoke_with_lm(
                self.card_a_generator,
                full_script=full_script,
                stage_title=stage.get("title", ""),
                npc_role=npc_role,
                scene_goal=stage.get("task", ""),
                key_points=stage_key_points_text,
                content_excerpt=retry_excerpt,
                is_guidance=is_guidance,
                include_prologue=include_prologue,
            )

        stage_meta = self._create_stage_meta(stage)
        return self._format_card_a(result, stage_index, stage_meta, stage)

    @Retryable(max_retries=3, exceptions=(Exception,))
    def generate_card_b(
        self,
        stage: dict,
        stage_index: int,
        total_stages: int,
        next_stage: Optional[dict],
        full_script: str,
    ) -> str:
        """生成 B 类卡片（场景过渡卡片）。"""
        is_last_stage = stage_index >= total_stages
        result = self._invoke_with_lm(
            self.card_b_generator,
            full_script=full_script,
            current_stage_title=stage.get("title", ""),
            current_stage_goal=stage.get("task", ""),
            current_stage_key_points=", ".join(stage.get("key_points", [])),
            current_stage_excerpt=stage.get("content_excerpt", ""),
            current_stage_role=stage.get("role", ""),
            next_stage_title=next_stage.get("title", "") if next_stage else "",
            next_stage_role=next_stage.get("role", "") if next_stage else "",
            is_last_stage=is_last_stage,
        )
        return self._format_card_b(result, stage_index, total_stages, stage=stage)

    def _generate_all_cards_impl(
        self,
        stages: List[dict],
        original_content: str,
        progress_callback=None,
        card_callback=None,
    ) -> str:
        """在专用线程内执行的实际生成逻辑。"""
        override = None
        if not (self.base_url and self.model):
            override = DEEPSEEK_API_KEY if self.model_type != "doubao" else DOUBAO_API_KEY
        self.lm = self._create_lm(api_key_override=override)
        reset_positive_feedback_history()

        all_cards = []
        total_stages = len(stages)

        for i, stage in enumerate(stages, 1):
            if progress_callback:
                progress_callback(i * 2 - 1, total_stages * 2, f"正在生成第{i}幕A类卡片（NPC角色）...")

            try:
                card_a = self.generate_card_a(stage, i, total_stages, original_content)
                block = f"# 卡片{i}A\n\n{card_a}"
                all_cards.append(block)
                if card_callback:
                    card_callback(f"卡片{i}A", block)
            except Exception as exc:
                error_card = f"# 卡片{i}A\n\n[生成失败: {exc}]\n"
                all_cards.append(error_card)
                if card_callback:
                    card_callback(f"卡片{i}A", error_card)
                if progress_callback:
                    progress_callback(i * 2 - 1, total_stages * 2, f"第{i}幕A类卡片生成失败，继续...")

            if progress_callback:
                progress_callback(i * 2, total_stages * 2, f"正在生成第{i}幕B类卡片（场景过渡）...")

            try:
                next_stage = stages[i] if i < total_stages else None
                card_b = self.generate_card_b(stage, i, total_stages, next_stage, original_content)
                block = f"# 卡片{i}B\n\n{card_b}"
                all_cards.append(block)
                if card_callback:
                    card_callback(f"卡片{i}B", block)
            except Exception as exc:
                if i == total_stages:
                    card_b = "# Context\n训练结束。\n\n# Output\n感谢您的参与。\n\n# Constraints\n- 结束"
                else:
                    card_b = f"[生成失败: {exc}]"
                block = f"# 卡片{i}B\n\n{card_b}"
                all_cards.append(block)
                if card_callback:
                    card_callback(f"卡片{i}B", block)
                if progress_callback:
                    progress_callback(i * 2, total_stages * 2, f"第{i}幕B类卡片生成失败，继续...")

        ending_num = total_stages + 1
        ending_label = f"卡片{ending_num}A"
        try:
            ending_card = self._generate_ending_card_a(stages, original_content)
            all_cards.append(ending_card)
            if card_callback:
                card_callback(ending_label, ending_card)
        except Exception as exc:
            fallback = (
                f"# {ending_label}\n\n"
                "# Role\n简单收尾角色。\n\n"
                "# Context\n本次实训到此结束。\n\n"
                "# Interaction\n感谢你的参与，今天就先到这里，我们下次再继续。\n\n"
                "# Transition\n说完这句话后结束本次实训，对话结束。\n\n"
                "# Constraints\n- 结束\n"
                f"<!-- ending_card_error: {exc} -->"
            )
            all_cards.append(fallback)
            if card_callback:
                card_callback(ending_label, fallback)

        all_cards = card_helpers.review_cross_card_style_diversity(all_cards)
        style_audit = card_helpers.build_style_audit_report(all_cards)
        print(
            "[风格审查] 机械表达命中总数="
            f"{style_audit.get('total_hits', 0)}，"
            f"明细={style_audit.get('counts', {})}"
        )
        return "\n\n---\n\n".join(all_cards)

    def generate_all_cards(
        self,
        stages: List[dict],
        original_content: str,
        progress_callback=None,
        card_callback=None,
    ) -> str:
        """生成所有阶段的 A/B 类卡片。"""
        return run_in_generation_context(
            self._generate_all_cards_impl,
            stages,
            original_content,
            progress_callback,
            card_callback,
        )
