"""
基于DSPy的卡片生成器
使用结构化签名和断言确保输出质量

DSPy优势：
1. 结构化输出：通过签名定义输入输出格式
2. 断言验证：确保输出不包含括号等违规内容
3. 可组合性：将复杂任务分解为模块
4. 自动优化：可通过优化器改进prompt效果
"""

import re
import json
import dspy
from typing import Optional, List
from dataclasses import dataclass

from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    MAX_TOKENS, TEMPERATURE
)


# ========== DSPy 签名定义 ==========

class CardASignature(dspy.Signature):
    """生成A类卡片（NPC角色卡片）的签名
    
    A类卡片是沉浸式角色扮演的核心，NPC需要自然地与学生对话。
    重要：每轮对话只问1-2个问题，避免让学生感到疲惫。
    """
    # 输入字段
    full_script: str = dspy.InputField(desc="完整的原始剧本内容")
    stage_index: int = dspy.InputField(desc="当前阶段编号（从1开始）")
    total_stages: int = dspy.InputField(desc="总阶段数")
    stage_title: str = dspy.InputField(desc="场景标题")
    npc_role: str = dspy.InputField(desc="NPC角色描述")
    scene_goal: str = dspy.InputField(desc="场景目标/任务")
    key_points: str = dspy.InputField(desc="关键剧情点，用逗号分隔")
    content_excerpt: str = dspy.InputField(desc="原文参考内容")
    next_card_id: str = dspy.InputField(desc="下一张卡片ID，如'卡片1B'")
    
    # 输出字段（人称约定：卡片给 NPC 用，「你」=NPC，「学生/对方」=学生，不用「我」）
    role_section: str = dspy.OutputField(desc="# Role 部分：NPC是谁，背景、性格、说话方式。50-100字。用「你」指代 NPC，例如「你是张经理，食品厂设备采购经理……」。")
    context_section: str = dspy.OutputField(desc="# Context 部分：当前场景背景，对方（学生）扮演什么角色。50-100字。用「你」指 NPC、「学生/对方」指学生。若本环节紧接在角色切换之后（上一张A卡是不同NPC），须写明：开场第一句须含简短情境承接（如时间、场景或身份，例如「好的，我们到病房了」「术后第二天了」「护士，我们明天要出院了」），再进入本角色第一句台词，避免学生感到突兀。")
    interaction_section: str = dspy.OutputField(desc="# Interaction 部分：你（NPC）如何与学生/对方对话、推进剧情。80-150字。用「你」指 NPC、「学生/对方」指学生。重要：每轮只问1-2个问题，不要连续追问。若本环节为学生向NPC咨询（如家属问护士出院指导），须写明每个主题追问不超过1～2轮、对方说清关键步骤后表示理解并感谢，避免对同一细节重复追问超过2次。")
    transition_section: str = dspy.OutputField(desc="# Transition 部分：什么情况下触发场景切换。用「你」指 NPC、「学生/对方」指学生。必须写明：仅在学生达到本环节核心目标（如完成关键任务、达到最低要求）时才输出下一张卡片；若未完成，写明「不要输出卡片XB，可继续追问/引导……」再给出跳转指令。50-80字。")
    constraints_section: str = dspy.OutputField(desc="# Constraints 部分：你（NPC）扮演时的限制和注意事项。使用短横线列表格式。必须包含：1）每轮只问1-2个问题；2）若本环节为引导型（如带教护士、医生提问学生），须包含「学生答对后至少追问1次为什么/依据/还需要注意什么，再进入下一问或下一环节」。")


class CardAPrologueSignature(dspy.Signature):
    """生成A类卡片开场白（仅用于第一张卡片）"""
    full_script: str = dspy.InputField(desc="完整的原始剧本内容")
    npc_role: str = dspy.InputField(desc="NPC角色描述")
    scene_goal: str = dspy.InputField(desc="场景目标/任务")
    
    prologue: str = dspy.OutputField(desc="开场白：NPC角色的自我介绍或场景引入，50-80字，用于在交互开始前展示给学生。不使用任何括号。")


class CardBSignature(dspy.Signature):
    """生成B类卡片（场景过渡卡片）的签名 - 用于同一角色的场景间过渡
    
    当前后A类卡片是同一角色时使用此签名，生成简洁的功能性过渡。
    重要：过渡语应根据上一环节实际对话表现来写——学生做得好就肯定，做得不好就简要指出问题，然后开启下一环节。不要一律中性或一律表扬，要根据事实。
    """
    # 输入字段
    full_script: str = dspy.InputField(desc="完整的原始剧本内容")
    stage_index: int = dspy.InputField(desc="当前阶段编号（从1开始）")
    total_stages: int = dspy.InputField(desc="总阶段数")
    current_stage_title: str = dspy.InputField(desc="当前阶段标题")
    current_stage_goal: str = dspy.InputField(desc="当前阶段目标")
    next_stage_title: str = dspy.InputField(desc="下一阶段标题（如果有）")
    next_card_id: str = dspy.InputField(desc="下一张卡片ID，如'卡片2A'或'结束'")
    is_last_stage: bool = dspy.InputField(desc="是否是最后一个阶段")
    
    # 输出字段 - 简洁版，无旁白；根据事实：好则肯定，不好则指出并开启下一步
    context_section: str = dspy.OutputField(desc="# Context 部分：说明本过渡语的使用原则。仅当学生达到本环节核心目标时才使用肯定式过渡；若明显未达标，先简短指出缺失再自然切换。不要使用「无论您是否……都是宝贵的」这类无条件推进表述。1-2句话。")
    output_section: str = dspy.OutputField(desc="# Output 部分：过渡语模板或示例，30-80字。需体现「根据事实」：可写两种表述（肯定版/指出不足版）或通用指引。正文不要包含「无论您是否……」；可用「您在本环节完成了……现在请……」或先指出不足再衔接。不要第三人称场景描写。")
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
    context_section: str = dspy.OutputField(desc="# Context 部分：说明本过渡语的使用原则。仅当学生达到本环节核心目标时才使用肯定式过渡；若明显未达标，先简短指出缺失再衔接角色切换。不要使用「无论您是否……都是宝贵的」这类无条件推进表述。1-2句话。")
    output_section: str = dspy.OutputField(desc="# Output 部分：过渡内容，50-80字。需体现「根据事实」；然后说明角色切换、介绍新角色。正文要简短、像场景提示，少用长段第三人称旁白（如「经过……现在请将注意力转向……」），以免打破沉浸感。可改为一句情境句（如「病房里，责任护士已备好报告」「术后第二天，患儿出现新情况」「病情稳定，母亲带着出院疑问等待沟通」）。不使用括号。")
    transition_section: str = dspy.OutputField(desc="# Transition 部分：仅包含跳转指令，格式为 **卡片XA** 或 **结束**")


# ========== 验证函数 ==========

def contains_brackets(text: str) -> bool:
    """检查文本是否包含括号（中文或英文）"""
    bracket_patterns = [
        r'（.*?）',  # 中文括号
        r'\(.*?\)',  # 英文括号
        r'【.*?】',  # 中文方括号
        r'\[.*?\]',  # 英文方括号
    ]
    for pattern in bracket_patterns:
        if re.search(pattern, text):
            return True
    return False


def strip_brackets(text: str) -> str:
    """移除文本中的括号及其内容，用于后处理 LLM 输出"""
    if not text:
        return text
    # 按顺序移除各类括号及其内容
    for pattern in [r'（.*?）', r'\(.*?\)', r'【.*?】', r'\[.*?\]']:
        text = re.sub(pattern, '', text)
    # 清理可能产生的多余空格或标点
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'[，。、；]\s*[，。、；]', '，', text)
    return text


def validate_no_brackets(text: str, field_name: str) -> bool:
    """验证文本不包含括号，用于DSPy断言"""
    if contains_brackets(text):
        dspy.Suggest(
            False,
            f"{field_name} 包含了括号内容，请移除所有括号描述（心理、动作、场景描写都不要用括号）"
        )
        return False
    return True


def validate_length(text: str, min_len: int, max_len: int, field_name: str) -> bool:
    """验证文本长度"""
    length = len(text)
    if length < min_len or length > max_len:
        dspy.Suggest(
            False,
            f"{field_name} 长度应在{min_len}-{max_len}字之间，当前为{length}字"
        )
        return False
    return True


# ========== DSPy 模块定义 ==========

class CardAGeneratorModule(dspy.Module):
    """A类卡片生成模块"""
    
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
        """生成A类卡片
        
        Args:
            full_script: 完整剧本
            stage_index: 当前阶段编号
            total_stages: 总阶段数
            stage_title: 场景标题
            npc_role: NPC角色
            scene_goal: 场景目标
            key_points: 关键点
            content_excerpt: 原文摘录
            include_prologue: 是否包含开场白（仅第一张卡片）
        """
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
        
        # 后处理：移除括号内容，避免因括号导致生成失败
        for field in ['role_section', 'context_section', 'interaction_section',
                      'transition_section', 'constraints_section']:
            text = getattr(result, field, '')
            if text and contains_brackets(text):
                setattr(result, field, strip_brackets(text))
        
        # 如果需要开场白（第一张卡片）
        prologue = ""
        if include_prologue:
            prologue_result = self.generate_prologue(
                full_script=full_script,
                npc_role=npc_role,
                scene_goal=scene_goal
            )
            prologue = prologue_result.prologue
            if prologue and contains_brackets(prologue):
                prologue = strip_brackets(prologue)
        
        return dspy.Prediction(
            role_section=result.role_section,
            context_section=result.context_section,
            interaction_section=result.interaction_section,
            transition_section=result.transition_section,
            constraints_section=result.constraints_section,
            prologue=prologue
        )


class CardBGeneratorModule(dspy.Module):
    """B类卡片生成模块
    
    根据前后A类卡片的角色是否相同，选择不同的生成策略：
    - 角色相同：简洁的功能性过渡（无旁白）
    - 角色不同：包含旁白的角色切换过渡
    """
    
    def __init__(self):
        super().__init__()
        self.generate_simple = dspy.Predict(CardBSignature)  # 简洁版（同一角色）
        self.generate_narrator = dspy.Predict(CardBNarratorSignature)  # 旁白版（不同角色）
    
    def _is_same_role(self, current_role: str, next_role: str) -> bool:
        """判断前后角色是否相同（模糊匹配）"""
        if not current_role or not next_role:
            return True  # 如果角色信息缺失，默认视为同一角色
        
        # 提取角色名称的核心部分进行比较
        # 例如 "陈新农，资深现代农业投资人" 和 "陈新农，一位经验丰富的投资人" 应该视为同一角色
        current_name = current_role.split('，')[0].split(',')[0].strip()
        next_name = next_role.split('，')[0].split(',')[0].strip()
        
        return current_name == next_name
    
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
        
        # 判断是否需要旁白（角色是否切换）
        use_narrator = not self._is_same_role(current_stage_role, next_stage_role) and not is_last_stage
        
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
            fields_to_check = ['role_section', 'context_section', 'output_section', 'transition_section']
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
            fields_to_check = ['context_section', 'output_section', 'transition_section']
        
        # 后处理：移除括号内容
        for field in fields_to_check:
            text = getattr(result, field, '')
            if text and contains_brackets(text):
                setattr(result, field, strip_brackets(text))
        
        # 标记是否使用了旁白
        result.use_narrator = use_narrator
        
        return result


# ========== 主卡片生成器类 ==========

class DSPyCardGenerator:
    """基于DSPy的卡片生成器"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化DSPy卡片生成器
        
        Args:
            api_key: API密钥，如果不提供则使用配置文件中的密钥
        """
        self.api_key = api_key or DEEPSEEK_API_KEY
        if not self.api_key:
            raise ValueError("未提供API密钥，请在.env文件中设置DEEPSEEK_API_KEY")
        
        # 配置DSPy使用DeepSeek
        self._configure_dspy()
        
        # 初始化生成模块
        self.card_a_generator = CardAGeneratorModule()
        self.card_b_generator = CardBGeneratorModule()
    
    def _configure_dspy(self):
        """配置DSPy使用DeepSeek API"""
        lm = dspy.LM(
            model=f"openai/{DEEPSEEK_MODEL}",
            api_key=self.api_key,
            api_base=DEEPSEEK_BASE_URL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE
        )
        dspy.configure(lm=lm)
    
    def _create_stage_meta(self, stage: dict) -> str:
        """创建阶段元数据块"""
        meta = {
            "stage_name": stage.get("title", ""),
            "description": stage.get("description", ""),
            "interaction_rounds": stage.get("interaction_rounds", 5),
        }
        return f"<!-- STAGE_META: {json.dumps(meta, ensure_ascii=False)} -->\n"
    
    def _format_card_a(self, result: dspy.Prediction, stage_index: int, stage_meta: str) -> str:
        """格式化A类卡片输出"""
        sections = []
        
        # 添加阶段元数据
        sections.append(stage_meta)
        
        # 如果有开场白（第一张卡片）
        if result.prologue:
            sections.append(f"# Prologue\n{result.prologue}\n")
        
        # 添加各个部分
        sections.append(f"# Role\n{result.role_section}\n")
        sections.append(f"# Context\n{result.context_section}\n")
        sections.append(f"# Interaction\n{result.interaction_section}\n")
        sections.append(f"# Transition\n{result.transition_section}\n当剧情自然进展到转折点时，仅输出：**卡片{stage_index}B**\n")
        
        # 确保Constraints包含关键约束
        constraints = result.constraints_section
        # 如果生成的约束中没有提问数量限制，添加它
        if "每轮" not in constraints and "问题" not in constraints:
            constraints = f"- **每轮只问1-2个问题**，避免连续追问让学生疲惫。\n{constraints}"
        # 若为引导型场景（带教、医生提问等），确保有深度追问约束
        if "追问" not in constraints and "为什么" not in constraints and "依据" not in constraints:
            constraints = f"- 学生答对后，至少追问1次「为什么/依据/还需要注意什么」，再进入下一问或下一环节。\n{constraints}"
        
        sections.append(f"# Constraints\n{constraints}")
        
        return "\n".join(sections)
    
    def _format_card_b(self, result: dspy.Prediction, stage_index: int, total_stages: int) -> str:
        """格式化B类卡片输出（不再包含 # Transition / **卡片XA**，避免对话中出现跳转指令）"""
        sections = []
        use_narrator = getattr(result, 'use_narrator', False)
        if use_narrator:
            # 旁白版：包含Role部分
            sections.append(f"# Role\n{result.role_section}\n")
            sections.append(f"# Context\n{result.context_section}\n")
            sections.append(f"# Output\n{result.output_section}\n")
            sections.append("# Constraints\n- **根据事实**：仅当学生达到本环节核心目标时才使用肯定式过渡；若明显未达标，先简短指出缺失再开启下一环节。不要使用「无论您是否……」类无条件推进表述。\n- **严禁任何括号内容**\n- **控制输出长度**：# Output部分50-80字\n- 所有文字都应该可以直接朗读出来")
        else:
            # 简洁版：无Role部分
            sections.append(f"# Context\n{result.context_section}\n")
            sections.append(f"# Output\n{result.output_section}\n")
            sections.append("# Constraints\n- **根据事实**：仅当学生达到本环节核心目标时才使用肯定式过渡；若明显未达标，先简短指出缺失再开启下一环节。不要使用「无论您是否……」类无条件推进表述。\n- **严禁任何括号内容**\n- **严禁第三人称描述或场景叙述**\n- **控制输出长度**：# Output部分30-80字\n- 所有文字都应该可以直接朗读出来")
        
        return "\n".join(sections)
    
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
        include_prologue = (stage_index == 1)  # 只有第一张卡片需要开场白
        
        try:
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
            return self._format_card_a(result, stage_index, stage_meta)
            
        except Exception as e:
            raise RuntimeError(f"生成A类卡片失败: {e}")
    
    def generate_card_b(self, stage: dict, stage_index: int, total_stages: int,
                        next_stage: Optional[dict], full_script: str) -> str:
        """
        生成B类卡片（场景过渡卡片）
        
        根据前后阶段的NPC角色是否相同，自动选择：
        - 角色相同：简洁的功能性过渡（无旁白）
        - 角色不同：包含旁白的角色切换过渡
        
        Args:
            stage: 当前阶段信息字典
            stage_index: 当前阶段索引（从1开始）
            total_stages: 总阶段数
            next_stage: 下一阶段信息（如果有）
            full_script: 完整的原始剧本内容
            
        Returns:
            生成的B类卡片内容
        """
        try:
            result = self.card_b_generator(
                full_script=full_script,
                stage_index=stage_index,
                total_stages=total_stages,
                current_stage_title=stage.get('title', ''),
                current_stage_goal=stage.get('task', ''),
                current_stage_role=stage.get('role', ''),  # 传递当前阶段角色
                next_stage_title=next_stage.get('title', '') if next_stage else '',
                next_stage_role=next_stage.get('role', '') if next_stage else ''
            )
            
            return self._format_card_b(result, stage_index, total_stages)
            
        except Exception as e:
            raise RuntimeError(f"生成B类卡片失败: {e}")
    
    def generate_all_cards(self, stages: List[dict], original_content: str,
                           progress_callback=None) -> str:
        """
        生成所有阶段的A/B类卡片
        
        Args:
            stages: 阶段信息列表
            original_content: 完整的原始剧本内容
            progress_callback: 进度回调函数，接收(current, total, message)参数
            
        Returns:
            合并后的所有卡片内容（A1-B1-A2-B2...格式）
        """
        all_cards = []
        total_stages = len(stages)
        
        for i, stage in enumerate(stages, 1):
            # 生成A类卡片
            if progress_callback:
                progress_callback(i * 2 - 1, total_stages * 2, 
                                f"正在生成第{i}幕A类卡片（NPC角色）...")
            
            card_a = self.generate_card_a(stage, i, total_stages, original_content)
            all_cards.append(f"# 卡片{i}A\n\n{card_a}")
            
            # 生成B类卡片
            if progress_callback:
                progress_callback(i * 2, total_stages * 2,
                                f"正在生成第{i}幕B类卡片（场景过渡）...")
            
            next_stage = stages[i] if i < total_stages else None
            card_b = self.generate_card_b(stage, i, total_stages, next_stage, original_content)
            all_cards.append(f"# 卡片{i}B\n\n{card_b}")
        
        # 用分隔线连接所有卡片
        return "\n\n---\n\n".join(all_cards)


# ========== 测试代码 ==========

if __name__ == "__main__":
    # 测试DSPy配置
    print("测试DSPy卡片生成器配置...")
    
    try:
        generator = DSPyCardGenerator()
        print("[OK] DSPy卡片生成器初始化成功")
        
        # 测试验证函数
        test_text_with_brackets = "这是一段（带括号的）文本"
        test_text_without_brackets = "这是一段不带括号的文本"
        
        print(f"[OK] 括号检测 - 有括号: {contains_brackets(test_text_with_brackets)}")
        print(f"[OK] 括号检测 - 无括号: {contains_brackets(test_text_without_brackets)}")
        
    except Exception as e:
        print(f"[ERROR] 初始化失败: {e}")
