"""
DSPy 卡片生成模块定义。

模块层负责把签名组合成可调用的 dspy.Module，并统一做输出后处理。
"""

import dspy

from .dspy_card_signatures import (
    CardASignature,
    CardAGuidanceSignature,
    CardAPrologueSignature,
    CardAEndingSignature,
    CardBSignature,
    CardBNarratorSignature,
)
from .dspy_utils import post_process_fields


class CardAGeneratorModule(dspy.Module):
    """A类卡片生成模块"""

    A_CARD_FIELDS = [
        "role_section",
        "context_section",
        "interaction_section",
        "transition_section",
        "constraints_section",
        "options_section",
    ]

    def __init__(self):
        super().__init__()
        self.generate_card = dspy.ChainOfThought(CardASignature)
        self.generate_guidance_card = dspy.ChainOfThought(CardAGuidanceSignature)
        self.generate_prologue = dspy.Predict(CardAPrologueSignature)

    def forward(
        self,
        full_script: str,
        stage_title: str,
        npc_role: str,
        scene_goal: str,
        key_points: str,
        content_excerpt: str,
        is_guidance: bool = False,
        include_prologue: bool = False,
    ) -> dspy.Prediction:
        """生成 A 类卡片。"""
        card_generator = self.generate_guidance_card if is_guidance else self.generate_card
        result = card_generator(
            full_script=full_script,
            stage_title=stage_title,
            npc_role=npc_role,
            scene_goal=scene_goal,
            key_points=key_points,
            content_excerpt=content_excerpt,
        )
        post_process_fields(result, self.A_CARD_FIELDS, inject_positive_feedback=True)

        prologue = ""
        if include_prologue:
            prologue_result = self.generate_prologue(
                full_script=full_script,
                npc_role=npc_role,
                scene_goal=scene_goal,
            )
            post_process_fields(prologue_result, ["prologue"], inject_positive_feedback=False)
            prologue = prologue_result.prologue

        return dspy.Prediction(
            role_section=result.role_section,
            context_section=result.context_section,
            interaction_section=result.interaction_section,
            transition_section=result.transition_section,
            constraints_section=result.constraints_section,
            options_section=result.options_section,
            prologue=prologue,
        )


class CardAEndingGeneratorModule(dspy.Module):
    """结尾 A 类卡片生成模块（轮次为0，仅收尾）"""

    ENDING_FIELDS = [
        "role_section",
        "context_section",
        "interaction_section",
        "transition_section",
        "constraints_section",
    ]

    def __init__(self):
        super().__init__()
        self.generate_ending = dspy.Predict(CardAEndingSignature)

    def forward(
        self,
        full_script: str,
        last_stage_title: str,
        last_stage_role: str,
        last_stage_goal: str,
        last_stage_key_points: str,
        last_stage_excerpt: str,
    ) -> dspy.Prediction:
        """生成结尾 A 类卡片（不包含 Prologue 和 Options）。"""
        result = self.generate_ending(
            full_script=full_script,
            last_stage_title=last_stage_title,
            last_stage_role=last_stage_role,
            last_stage_goal=last_stage_goal,
            last_stage_key_points=last_stage_key_points,
            last_stage_excerpt=last_stage_excerpt,
        )
        post_process_fields(result, self.ENDING_FIELDS, inject_positive_feedback=False)
        return result


class CardBGeneratorModule(dspy.Module):
    """B类卡片生成模块"""

    NARRATOR_FIELDS = ["role_section", "context_section", "output_section"]
    SIMPLE_FIELDS = ["context_section", "output_section"]

    def __init__(self):
        super().__init__()
        self.generate_simple = dspy.Predict(CardBSignature)
        self.generate_narrator = dspy.Predict(CardBNarratorSignature)

    def forward(
        self,
        full_script: str,
        current_stage_title: str,
        current_stage_goal: str,
        current_stage_key_points: str = "",
        current_stage_excerpt: str = "",
        current_stage_role: str = "",
        next_stage_title: str = "",
        next_stage_role: str = "",
        is_last_stage: bool = False,
    ) -> dspy.Prediction:
        """生成 B 类卡片。

        `full_script` 为兼容旧调用保留，但 B 卡 signature 已不再消费。
        """
        if is_last_stage:
            return dspy.Prediction(
                context_section="以当前NPC身份自然收尾并感谢学生，不要再开启新任务。",
                output_section="好，那我们今天就先到这里，辛苦了。",
                use_narrator=False,
            )

        # 当前统一使用简洁版 B 卡；保留 narrator 分支是为了兼容后续实验切换。
        use_narrator = False

        if use_narrator:
            result = self.generate_narrator(
                current_stage_title=current_stage_title,
                current_stage_goal=current_stage_goal,
                current_stage_key_points=current_stage_key_points,
                current_stage_excerpt=current_stage_excerpt,
                current_stage_role=current_stage_role,
                next_stage_title=next_stage_title,
                next_stage_role=next_stage_role,
            )
            post_process_fields(result, self.NARRATOR_FIELDS, inject_positive_feedback=False)
        else:
            result = self.generate_simple(
                current_stage_title=current_stage_title,
                current_stage_goal=current_stage_goal,
                current_stage_key_points=current_stage_key_points,
                current_stage_excerpt=current_stage_excerpt,
                next_stage_title=next_stage_title,
            )
            post_process_fields(result, self.SIMPLE_FIELDS, inject_positive_feedback=False)

        result.use_narrator = use_narrator
        return result
