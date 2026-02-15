"""
基于DSPy的卡片生成器
使用结构化签名和断言确保输出质量

优化点：
1. 统一后处理逻辑，避免重复代码
2. 最后一幕B卡片跳过LLM调用，直接返回"结束"
3. 使用实例级LM配置，避免全局竞态条件
4. 移除死代码（未使用的验证函数）
5. 长度约束改为建议而非强制
"""

import re
import json
import threading
from concurrent.futures import ThreadPoolExecutor
import dspy
from typing import Optional, List

# 全局锁：dspy.configure 为全局状态，并发时需串行化 LM 配置与调用
_dspy_lm_lock = threading.Lock()

# 单线程执行器：dspy.settings 为线程局部，只能由"最初配置"的线程修改。
# FastAPI/uvicorn 多线程处理请求时，不同请求可能在不同线程，导致 "can only be changed by the thread that initially configured it"。
# 所有卡片生成必须在此专用线程内执行，确保 dspy.configure 与 LLM 调用在同一线程。
_dspy_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dspy-card-gen")

from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    DOUBAO_API_KEY, DOUBAO_BASE_URL, DOUBAO_MODEL,
    DEFAULT_MODEL_TYPE, MAX_TOKENS, TEMPERATURE
)
from .dspy_utils import (
    post_process_fields,
    is_same_role,
    Retryable,
    format_card_section,
    ensure_constraint
)


# ========== DSPy 签名定义 ==========

class CardASignature(dspy.Signature):
    """生成A类卡片（NPC角色卡片）的签名
    
    A类卡片是沉浸式角色扮演的核心，NPC需要自然地与学生对话。
    重要：每轮对话只问1-2个问题，避免让学生感到疲惫。
    """
    # 输入字段
    full_script: str = dspy.InputField(desc="完整的原始剧本内容，用于理解整体剧情与学习目标。")
    stage_index: int = dspy.InputField(desc="当前阶段编号（从1开始）")
    total_stages: int = dspy.InputField(desc="总阶段数")
    stage_title: str = dspy.InputField(desc="场景标题")
    npc_role: str = dspy.InputField(desc="NPC角色描述")
    scene_goal: str = dspy.InputField(desc="场景目标/任务")
    key_points: str = dspy.InputField(desc="关键剧情点，用逗号分隔。后续输出时应尽量逐条覆盖这些要点，不要只做笼统概括。")
    content_excerpt: str = dspy.InputField(desc="本幕对应的原文关键内容或对话摘要，是必须重点覆盖的参考段落。生成各部分时，应优先从此处提取具体事实、数据、术语和对话片段，而不是只做抽象总结。")
    next_card_id: str = dspy.InputField(desc="下一张卡片ID，如'卡片1B'")

    # 输出字段（人称约定：卡片给 NPC 用，「你」=NPC，「学生/对方」=学生，不用「我」）
    role_section: str = dspy.OutputField(desc="# Role 部分：NPC是谁，背景、性格、说话方式。建议50-100字，简洁自然即可。用「你」指代 NPC，例如「你是张经理，食品厂设备采购经理……」。需要结合本幕 `content_excerpt` 与 `key_points` 中的关键信息，避免过度抽象的人设描述。")
    context_section: str = dspy.OutputField(desc="# Context 部分：当前场景背景，对方（学生）扮演什么角色。建议50-100字。用「你」指 NPC、「学生/对方」指学生。须嵌入本幕原文中的关键信息点（如角色关系、场景前提、重要道具/数据），而不是只写「你和学生正在交流」这类空泛语句。若本环节紧接在角色切换之后（上一张A卡是不同NPC），须写明：开场第一句须含简短情境承接（如时间、场景或身份，例如「好的，我们到病房了」「术后第二天了」「护士，我们明天要出院了」），再进入本角色第一句台词，避免学生感到突兀。")
    interaction_section: str = dspy.OutputField(desc="# Interaction 部分：你（NPC）如何与学生/对方对话、推进剧情。建议80-150字。用「你」指 NPC、「学生/对方」指学生。重要：1）每轮只问1-2个问题，不要连续追问；2）严禁使用机械连接词如「你提到」「这两点直接关系到」「第一...第二...」等重复句式；3）学生回答正确时给予具体正向激励，如「这个思路很清晰」「数据支撑很好」等；4）若本环节为学生向NPC咨询（如家属问护士出院指导），须写明每个主题追问不超过1～2轮、对方说清关键步骤后表示理解并感谢，避免对同一细节重复追问超过2次；5）在对话中逐一渗透 `key_points` 中列出的要点，可通过具体提问、解释或小结把每个要点讲清楚，避免只用一句「按要求完成即可」之类的概括性说法。")
    transition_section: str = dspy.OutputField(desc="# Transition 部分：什么情况下触发场景切换。用「你」指 NPC、「学生/对方」指学生。必须基于本幕关键知识点和任务目标来判断是否达标：明确写出学生需要展示哪些要点（可引用 `key_points` 或 `content_excerpt` 中的关键信息）才算完成本环节。仅在学生达到本环节核心目标（如完成关键任务、达到最低要求）时才输出下一张卡片；若未完成，写明「不要输出卡片XB，可继续追问/引导……」再给出跳转指令。建议50-80字。")
    constraints_section: str = dspy.OutputField(desc="# Constraints 部分：你（NPC）扮演时的限制和注意事项。使用短横线列表格式。必须包含：1）每轮只问1-2个问题，每轮回复控制在250字以内；2）严禁使用以下机械连接词：「你提到」「这两点直接关系到」「第一...第二...」「哦？」等；3）学生回答正确时给予具体正向激励（如「很好」「思路清晰」「数据准确」），每2-3轮至少一次；4）若本环节为引导型（如带教护士、医生提问学生），须包含「学生答对后至少追问1次为什么/依据/还需要注意什么，再进入下一问或下一环节」；5）使用多样化的自然表达，避免重复句式；6）确保在本幕对话过程中覆盖 `key_points` 和 `content_excerpt` 中的关键信息点，不得只给出抽象总结，如有尚未覆盖的要点，应在后续轮次中补充。")
    options_section: str = dspy.OutputField(desc="# Options（可选）部分：仅当涉及英文/代码/长串需语音输入时提供。列出 3-5 个编号选项，中文描述清晰，包含正确/常见误区/部分正确。若无需选项则返回空字符串。避免让学生朗读英文或代码，提示其说编号或简短中文。")


class CardAPrologueSignature(dspy.Signature):
    """生成A类卡片开场白（仅用于第一张卡片）"""
    full_script: str = dspy.InputField(desc="完整的原始剧本内容")
    npc_role: str = dspy.InputField(desc="NPC角色描述")
    scene_goal: str = dspy.InputField(desc="场景目标/任务")

    prologue: str = dspy.OutputField(desc="开场白：NPC角色的自我介绍或场景引入，建议50-80字，用于在交互开始前展示给学生。不使用任何括号。")


class CardBSignature(dspy.Signature):
    """生成B类卡片（场景过渡卡片）的签名 - 用于同一角色的场景间过渡
    
    当前后A类卡片是同一角色时使用此签名，生成简洁的功能性过渡。
    重要：过渡语应根据上一环节实际对话表现来写——学生做得好就肯定，做得不好就简要指出问题，然后开启下一环节。不要一律中性或一律表扬，要根据事实。
    """
    # 输入字段
    full_script: str = dspy.InputField(desc="完整的原始剧本内容")
    stage_index: int = dspy.InputField(desc="当前阶段编号（从1开始）")
    total_stages: int = dspy.InputField(desc="总阶段数")
    current_stage_title: str = dspy.InputField(desc="当前阶段标题，用于在过渡语中点明本环节完成了什么。")
    current_stage_goal: str = dspy.InputField(desc="当前阶段目标，应与该阶段的 key_points 和任务描述对应，过渡语需要根据是否达成这些目标来选择不同表述。")
    next_stage_title: str = dspy.InputField(desc="下一阶段标题（如果有）")
    next_card_id: str = dspy.InputField(desc="下一张卡片ID，如'卡片2A'或'结束'")
    is_last_stage: bool = dspy.InputField(desc="是否是最后一个阶段")

    # 输出字段 - 简洁版，无旁白；根据事实：好则肯定，不好则指出并开启下一步
    context_section: str = dspy.OutputField(desc="# Context 部分：说明本过渡语的使用原则。仅当学生达到本环节核心目标（可结合本阶段 key_points 与任务目标判断）时才使用肯定式过渡；若明显未达标，先简短点出缺失的要点再自然切换。不要使用「无论您是否……都是宝贵的」这类无条件推进表述。1-2句话。")
    output_section: str = dspy.OutputField(desc="# Output 部分：过渡语模板或示例，建议30-80字。需体现「根据事实」：可写两种表述（肯定版/指出不足版）或通用指引。正文不要包含「无论您是否……」；可用「您在本环节已经完成了……（点出1-2个关键要点）现在请……」或先指出未达成的关键点再衔接。不要第三人称场景描写。")
    transition_section: str = dspy.OutputField(desc="# Transition 部分：仅包含跳转指令，格式为 **卡片XA** 或 **结束**")


class CardBNarratorSignature(dspy.Signature):
    """生成B类卡片（旁白过渡卡片）的签名 - 用于不同角色之间的切换
    
    当前后A类卡片是不同角色时使用此签名，需要旁白来衔接角色转换。
    重要：过渡语应根据上一环节实际表现——学生做得好就肯定，做得不好就简要指出问题，然后开启下一环节、介绍新角色。根据事实，不要一律中性或一律表扬。
    """
    # 输入字段
    full_script: str = dspy.InputField(desc="完整的原始剧本内容")
    stage_index: int = dspy.InputField(desc="当前阶段编号（从1开始）")
    total_stages: int = dspy.InputField(desc="总阶段数")
    current_stage_title: str = dspy.InputField(desc="当前阶段标题")
    current_stage_goal: str = dspy.InputField(desc="当前阶段目标")
    current_stage_role: str = dspy.InputField(desc="当前阶段NPC角色")
    next_stage_title: str = dspy.InputField(desc="下一阶段标题（如果有）")
    next_stage_role: str = dspy.InputField(desc="下一阶段NPC角色（如果有）")
    next_card_id: str = dspy.InputField(desc="下一张卡片ID，如'卡片2A'或'结束'")
    is_last_stage: bool = dspy.InputField(desc="是否是最后一个阶段")

    # 输出字段 - 旁白版，用于角色切换；根据事实：好则肯定，不好则指出并开启下一步
    role_section: str = dspy.OutputField(desc="# Role 部分：旁白/叙述者的定位，1句话。")
    context_section: str = dspy.OutputField(desc="# Context 部分：说明本过渡语的使用原则。仅当学生达到本环节核心目标（可结合本阶段 key_points 与任务目标判断）时才使用肯定式过渡；若明显未达标，先简短指出缺失的关键要点再衔接角色切换。不要使用「无论您是否……都是宝贵的」这类无条件推进表述。1-2句话。")
    output_section: str = dspy.OutputField(desc="# Output 部分：过渡内容，建议50-80字。需体现「根据事实」：可以分别给出学生表现较好和需要改进两种简短表述，并点明上一阶段达成或遗漏的关键要点；然后说明角色切换、介绍新角色。正文要简短、像场景提示，少用长段第三人称旁白（如「经过……现在请将注意力转向……」），以免打破沉浸感。可改为一句情境句（如「病房里，责任护士已备好报告」「术后第二天，患儿出现新情况」「病情稳定，母亲带着出院疑问等待沟通」）。不使用括号。")
    transition_section: str = dspy.OutputField(desc="# Transition 部分：仅包含跳转指令，格式为 **卡片XA** 或 **结束**")


# ========== DSPy 模块定义 ==========

class CardAGeneratorModule(dspy.Module):
    """A类卡片生成模块"""

    A_CARD_FIELDS = ['role_section', 'context_section', 'interaction_section',
                     'transition_section', 'constraints_section', 'options_section']

    def __init__(self):
        super().__init__()
        self.generate_card = dspy.ChainOfThought(CardASignature)
        self.generate_prologue = dspy.Predict(CardAPrologueSignature)

    def forward(
        self,
        full_script: str,
        stage_index: int,
        total_stages: int,
        stage_title: str,
        npc_role: str,
        scene_goal: str,
        key_points: str,
        content_excerpt: str,
        include_prologue: bool = False
    ) -> dspy.Prediction:
        """生成A类卡片"""
        next_card_id = f"卡片{stage_index}B"

        # 生成卡片主体
        result = self.generate_card(
            full_script=full_script,
            stage_index=stage_index,
            total_stages=total_stages,
            stage_title=stage_title,
            npc_role=npc_role,
            scene_goal=scene_goal,
            key_points=key_points,
            content_excerpt=content_excerpt,
            next_card_id=next_card_id
        )

        # 后处理：移除括号内容
        post_process_fields(result, self.A_CARD_FIELDS)

        # 如果需要开场白（第一张卡片）
        prologue = ""
        if include_prologue:
            prologue_result = self.generate_prologue(
                full_script=full_script,
                npc_role=npc_role,
                scene_goal=scene_goal
            )
            prologue = prologue_result.prologue
            post_process_fields(prologue_result, ['prologue'])
            prologue = prologue_result.prologue

        return dspy.Prediction(
            role_section=result.role_section,
            context_section=result.context_section,
            interaction_section=result.interaction_section,
            transition_section=result.transition_section,
            constraints_section=result.constraints_section,
            options_section=result.options_section,
            prologue=prologue
        )


class CardBGeneratorModule(dspy.Module):
    """B类卡片生成模块

    根据前后A类卡片的角色是否相同，选择不同的生成策略：
    - 角色相同：简洁的功能性过渡（无旁白）
    - 角色不同：包含旁白的角色切换过渡
    - 最后一幕：直接返回"结束"，跳过LLM调用
    """

    NARRATOR_FIELDS = ['role_section', 'context_section', 'output_section', 'transition_section']
    SIMPLE_FIELDS = ['context_section', 'output_section', 'transition_section']

    def __init__(self):
        super().__init__()
        self.generate_simple = dspy.Predict(CardBSignature)
        self.generate_narrator = dspy.Predict(CardBNarratorSignature)

    def forward(
        self,
        full_script: str,
        stage_index: int,
        total_stages: int,
        current_stage_title: str,
        current_stage_goal: str,
        current_stage_role: str = "",
        next_stage_title: str = "",
        next_stage_role: str = ""
    ) -> dspy.Prediction:
        """生成B类卡片"""
        is_last_stage = stage_index >= total_stages
        next_card_id = "结束" if is_last_stage else f"卡片{stage_index + 1}A"

        # 优化：最后一幕直接返回固定结果，不调用LLM
        if is_last_stage:
            return dspy.Prediction(
                context_section="本环节结束，训练完成。",
                output_section="训练结束，感谢您的参与。",
                transition_section="**结束**",
                use_narrator=False
            )

        # 判断是否需要旁白（角色是否切换）
        use_narrator = not is_same_role(current_stage_role, next_stage_role)

        if use_narrator:
            # 角色不同，使用旁白版
            result = self.generate_narrator(
                full_script=full_script,
                stage_index=stage_index,
                total_stages=total_stages,
                current_stage_title=current_stage_title,
                current_stage_goal=current_stage_goal,
                current_stage_role=current_stage_role,
                next_stage_title=next_stage_title,
                next_stage_role=next_stage_role,
                next_card_id=next_card_id,
                is_last_stage=is_last_stage
            )
            post_process_fields(result, self.NARRATOR_FIELDS)
        else:
            # 角色相同，使用简洁版
            result = self.generate_simple(
                full_script=full_script,
                stage_index=stage_index,
                total_stages=total_stages,
                current_stage_title=current_stage_title,
                current_stage_goal=current_stage_goal,
                next_stage_title=next_stage_title,
                next_card_id=next_card_id,
                is_last_stage=is_last_stage
            )
            post_process_fields(result, self.SIMPLE_FIELDS)

        # 标记是否使用了旁白
        result.use_narrator = use_narrator

        return result


# ========== 主卡片生成器类 ==========

class DSPyCardGenerator:
    """基于DSPy的卡片生成器
    
    支持多模型配置：DeepSeek 或 豆包(Doubao)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_type: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        初始化DSPy卡片生成器。支持统一 LLM 配置（model_type 为 openai 时用 base_url + model）。
        """
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

        # 初始化生成模块（传入LM以避免全局配置）
        self.card_a_generator = CardAGeneratorModule()
        self.card_b_generator = CardBGeneratorModule()

    def _create_lm(self, api_key_override: Optional[str] = None) -> dspy.LM:
        """创建LM实例。支持 doubao / deepseek / 自定义 base_url+model。"""
        key = api_key_override or self.api_key
        if self.base_url and self.model:
            return dspy.LM(
                model=f"openai/{self.model}",
                api_key=key,
                api_base=self.base_url,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE
            )
        if self.model_type == "doubao":
            key = key or DOUBAO_API_KEY
            return dspy.LM(
                model=f"openai/{DOUBAO_MODEL}",
                api_key=key,
                api_base=DOUBAO_BASE_URL,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE
            )
        key = key or DEEPSEEK_API_KEY
        return dspy.LM(
            model=f"openai/{DEEPSEEK_MODEL}",
            api_key=key,
            api_base=DEEPSEEK_BASE_URL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE
        )

    def _create_stage_meta(self, stage: dict) -> str:
        """创建阶段元数据块"""
        meta = {
            "stage_name": stage.get("title", ""),
            "description": stage.get("description", ""),
            "interaction_rounds": stage.get("interaction_rounds", 5),
        }
        return f"<!-- STAGE_META: {json.dumps(meta, ensure_ascii=False)} -->\n"

    def _format_card_a(self, result: dspy.Prediction, stage_index: int, stage_meta: str, stage: dict) -> str:
        """格式化A类卡片输出，并基于原始阶段信息做覆盖度自检"""
        sections = []

        # 添加阶段元数据
        sections.append(stage_meta)

        # 如果有开场白（第一张卡片）
        if result.prologue:
            sections.append(format_card_section("Prologue", result.prologue))

        # 添加各个部分
        sections.append(format_card_section("Role", result.role_section))
        sections.append(format_card_section("Context", result.context_section))
        sections.append(format_card_section("Interaction", result.interaction_section))
        sections.append(format_card_section("Transition", result.transition_section))
        sections.append(f"当剧情自然进展到转折点时，仅输出：**卡片{stage_index}B**\n")

        # 可选的编号选项，帮助语音环境下避免朗读英文/代码
        if getattr(result, "options_section", ""):
            sections.append(format_card_section("Options", result.options_section))

        # 确保Constraints包含关键约束
        constraints = result.constraints_section
        constraints = ensure_constraint(
            constraints, "每轮",
            "**每轮只问1-2个问题**，避免连续追问让学生疲惫。"
        )
        constraints = ensure_constraint(
            constraints, "追问",
            "学生答对后，至少追问1次「为什么/依据/还需要注意什么」，再进入下一问或下一环节。"
        )
        constraints = ensure_constraint(
            constraints, "编号",
            "涉及英文/代码/长串时，必须提供编号选项，引导学生说编号或简短中文，不要要求朗读原文。"
        )
        constraints = ensure_constraint(
            constraints, "角色",
            "你（NPC）只负责提问、点评或引导，不要替对方（剧情中的角色，由剧本设定）说出答案、思路或设计方案。"
        )
        # 基于 key_points 与 content_excerpt 做简单覆盖度自检：
        # 抽取若干原文要点，若在各段落中未直接出现，则在约束中提醒需要特别关注。
        try:
            coverage_hints: List[str] = []
            stage_key_points = stage.get("key_points") or []
            if isinstance(stage_key_points, list):
                for kp in stage_key_points:
                    if isinstance(kp, str):
                        text = kp.strip()
                        if len(text) >= 2:
                            coverage_hints.append(text[:40])
                    if len(coverage_hints) >= 6:
                        break
            # 若 key_points 不足，则从 content_excerpt 中补充 1-2 个较长片段
            if len(coverage_hints) < 3:
                excerpt = str(stage.get("content_excerpt") or "").strip()
                if excerpt:
                    candidates = re.split(r"[，。；;,.、\n]", excerpt)
                    for c in candidates:
                        t = c.strip()
                        if 4 <= len(t) <= 30 and t not in coverage_hints:
                            coverage_hints.append(t)
                        if len(coverage_hints) >= 6:
                            break
            # 检查这些要点是否已在当前输出中直接出现
            if coverage_hints:
                combined = " ".join(
                    [
                        result.role_section or "",
                        result.context_section or "",
                        result.interaction_section or "",
                        result.transition_section or "",
                    ]
                )
                missing = [p for p in coverage_hints if p and p not in combined]
                if missing:
                    display = "、".join(missing[:6])
                    coverage_text = (
                        f"在实际对话与反馈中，请特别确保围绕以下原文要点展开，"
                        f"不得只作概括性说明：{display}。"
                    )
                    constraints = ensure_constraint(constraints, "原文要点", coverage_text)
        except Exception:
            # 自检失败不应影响正常生成，静默忽略
            pass

        sections.append(format_card_section("Constraints", constraints))

        return "\n\n".join(sections)

    def _truncate_text(self, text: str, max_len: int = 250) -> str:
        """Truncate text to max_len, attempting to cut at sentence boundary."""
        if not text:
            return text
        if len(text) <= max_len:
            return text
        cut = text.rfind('。', 0, max_len)
        if cut == -1:
            cut = max_len - 3
        return text[:cut].rstrip() + "..."

    def _format_card_b(self, result: dspy.Prediction, stage_index: int, total_stages: int) -> str:
        """格式化B类卡片输出（不再包含 # Transition / **卡片XA**，避免对话中出现跳转指令）"""
        sections = []
        use_narrator = getattr(result, 'use_narrator', False)

        if use_narrator:
            # 旁白版：包含Role部分
            sections.append(format_card_section("Role", result.role_section))
            sections.append(format_card_section("Context", result.context_section))
            sections.append(format_card_section("Output", result.output_section))
            sections.append(format_card_section("Constraints",
                "- **根据事实**：仅当学生达到本环节核心目标时才使用肯定式过渡；若明显未达标，先简短指出缺失的关键要点再开启下一环节。不要使用「无论您是否……」类无条件推进表述。\n"
                "- **避免长篇旁白**：优先用1-2句简短情境提示和评价，不要写大段第三人称叙述，以免打断沉浸感。\n"
                "- **过渡语可准备两个版本**：在模板中分别给出“表现较好”和“需要改进”两种简短表述，方便根据学生实际表现选择。\n"
                "- **严禁任何括号内容**\n"
                "- **控制输出长度**：# Output部分50-80字\n"
                "- 所有文字都应该可以直接朗读出来"
            ))
        else:
            # 简洁版：无Role部分
            sections.append(format_card_section("Context", result.context_section))
            sections.append(format_card_section("Output", result.output_section))
            sections.append(format_card_section("Constraints",
                "- **根据事实**：仅当学生达到本环节核心目标时才使用肯定式过渡；若明显未达标，先简短指出缺失的关键要点再开启下一环节。不要使用「无论您是否……」类无条件推进表述。\n"
                "- **严禁任何括号内容**\n"
                "- **严禁第三人称长篇场景叙述**：可以用一句情境提示，但不要写成旁白段落。\n"
                "- **控制输出长度**：# Output部分30-80字\n"
                "- 如有需要，可在模板中准备“表现较好/需要改进”两个简短版本，便于根据学生表现选择。\n"
                "- 所有文字都应该可以直接朗读出来"
            ))

        return "\n".join(sections)

    @Retryable(max_retries=3, exceptions=(Exception,))
    def generate_card_a(self, stage: dict, stage_index: int, total_stages: int,
                        full_script: str) -> str:
        """
        生成A类卡片（NPC角色卡片）

        Args:
            stage: 阶段信息字典
            stage_index: 当前阶段索引（从1开始）
            total_stages: 总阶段数
            full_script: 完整的原始剧本内容

        Returns:
            生成的A类卡片内容
        """
        include_prologue = (stage_index == 1)

        with _dspy_lm_lock:
            dspy.configure(lm=self.lm)
            result = self.card_a_generator(
                full_script=full_script,
                stage_index=stage_index,
                total_stages=total_stages,
                stage_title=stage.get('title', ''),
                npc_role=stage.get('role', ''),
                scene_goal=stage.get('task', ''),
                key_points=', '.join(stage.get('key_points', [])),
                content_excerpt=stage.get('content_excerpt', ''),
                include_prologue=include_prologue
            )

        stage_meta = self._create_stage_meta(stage)
        return self._format_card_a(result, stage_index, stage_meta, stage)

    @Retryable(max_retries=3, exceptions=(Exception,))
    def generate_card_b(self, stage: dict, stage_index: int, total_stages: int,
                        next_stage: Optional[dict], full_script: str) -> str:
        """
        生成B类卡片（场景过渡卡片）

        Args:
            stage: 当前阶段信息字典
            stage_index: 当前阶段索引（从1开始）
            total_stages: 总阶段数
            next_stage: 下一阶段信息（如果有）
            full_script: 完整的原始剧本内容

        Returns:
            生成的B类卡片内容
        """
        with _dspy_lm_lock:
            dspy.configure(lm=self.lm)
            result = self.card_b_generator(
                full_script=full_script,
                stage_index=stage_index,
                total_stages=total_stages,
                current_stage_title=stage.get('title', ''),
                current_stage_goal=stage.get('task', ''),
                current_stage_role=stage.get('role', ''),
                next_stage_title=next_stage.get('title', '') if next_stage else '',
                next_stage_role=next_stage.get('role', '') if next_stage else ''
            )

        return self._format_card_b(result, stage_index, total_stages)

    def _generate_all_cards_impl(self, stages: List[dict], original_content: str,
                                 progress_callback=None) -> str:
        """
        在专用线程内执行的实际生成逻辑（供 generate_all_cards 调用）
        """
        # Bootstrap 等优化器会对 program 做 deepcopy，self.api_key 可能失效。
        # 自定义 base_url+model 时用 self.api_key，否则从 config 取最新 key。
        override = None
        if not (self.base_url and self.model):
            override = DEEPSEEK_API_KEY if self.model_type != "doubao" else DOUBAO_API_KEY
        self.lm = self._create_lm(api_key_override=override)

        all_cards = []
        total_stages = len(stages)

        for i, stage in enumerate(stages, 1):
            # 生成A类卡片
            if progress_callback:
                progress_callback(i * 2 - 1, total_stages * 2,
                                f"正在生成第{i}幕A类卡片（NPC角色）...")

            try:
                card_a = self.generate_card_a(stage, i, total_stages, original_content)
                all_cards.append(f"# 卡片{i}A\n\n{card_a}")
            except Exception as e:
                # 降级：返回错误提示但继续执行
                error_card = f"# 卡片{i}A\n\n[生成失败: {e}]\n"
                all_cards.append(error_card)
                if progress_callback:
                    progress_callback(i * 2 - 1, total_stages * 2,
                                    f"第{i}幕A类卡片生成失败，继续...")

            # 生成B类卡片
            if progress_callback:
                progress_callback(i * 2, total_stages * 2,
                                f"正在生成第{i}幕B类卡片（场景过渡）...")

            try:
                next_stage = stages[i] if i < total_stages else None
                card_b = self.generate_card_b(stage, i, total_stages, next_stage, original_content)
                all_cards.append(f"# 卡片{i}B\n\n{card_b}")
            except Exception as e:
                # 降级：对于最后一幕，生成简单的结束卡片
                if i == total_stages:
                    card_b = "# Context\n训练结束。\n\n# Output\n感谢您的参与。\n\n# Constraints\n- 结束"
                else:
                    card_b = f"[生成失败: {e}]"
                all_cards.append(f"# 卡片{i}B\n\n{card_b}")
                if progress_callback:
                    progress_callback(i * 2, total_stages * 2,
                                    f"第{i}幕B类卡片生成失败，继续...")

        # 用分隔线连接所有卡片
        return "\n\n---\n\n".join(all_cards)

    def generate_all_cards(self, stages: List[dict], original_content: str,
                           progress_callback=None) -> str:
        """
        生成所有阶段的A/B类卡片。

        当由非主线程调用时（如 FastAPI 请求处理线程），通过单线程执行器执行，
        避免 dspy.settings「只能由最初配置的线程修改」导致的生成失败。
        主线程调用（CLI、优化器）则直接执行。
        """
        if threading.current_thread() is threading.main_thread():
            return self._generate_all_cards_impl(stages, original_content, progress_callback)
        future = _dspy_executor.submit(
            self._generate_all_cards_impl,
            stages,
            original_content,
            progress_callback,
        )
        return future.result()


# ========== 测试代码 ==========

if __name__ == "__main__":
    # 测试DSPy配置
    print("测试DSPy卡片生成器配置...")

    try:
        generator = DSPyCardGenerator()
        print("[OK] DSPy卡片生成器初始化成功")
        print(f"[OK] 实例级LM配置: {generator.lm is not None}")

    except Exception as e:
        print(f"[ERROR] 初始化失败: {e}")
