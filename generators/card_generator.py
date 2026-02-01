"""
卡片生成器
基于沉浸式角色扮演模式，根据完整剧本生成A类（NPC角色）和B类（场景过渡）卡片
"""
import os
import json
from typing import Optional

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    MAX_TOKENS, TEMPERATURE, TEMPLATES_DIR
)


class CardGenerator:
    """
    卡片生成器类
    基于"沉浸式角色扮演教学平台"理念生成卡片
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化卡片生成器
        
        Args:
            api_key: DeepSeek API密钥，如果不提供则使用配置文件中的密钥
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("请先安装openai库: pip install openai")
        
        self.api_key = api_key or DEEPSEEK_API_KEY
        if not self.api_key:
            raise ValueError("未提供API密钥，请在.env文件中设置DEEPSEEK_API_KEY")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=DEEPSEEK_BASE_URL
        )
        
        # 加载系统上下文（平台理解文档）
        self.system_context = self._load_template("system_context.md")
    
    def _load_template(self, template_name: str) -> str:
        """加载模板文件"""
        template_path = os.path.join(TEMPLATES_DIR, template_name)
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"模板文件不存在: {template_path}")
        
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        """
        调用DeepSeek API（使用system和user两个角色）
        
        Args:
            system_prompt: 系统提示词（让LLM理解平台）
            user_prompt: 用户提示词（具体任务）
            
        Returns:
            API返回的文本内容
        """
        response = self.client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    
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
        next_card = f"卡片{stage_index}B"
        
        # 确定学生扮演的角色（如果剧本中有指定）
        student_role_hint = ""
        if "student_role" in stage:
            student_role_hint = f"- 学生扮演的角色：{stage['student_role']}"
        
        # 为第一张卡片添加开场白要求
        is_first_card = stage_index == 1
        prologue_requirement = ""
        prologue_output_section = ""
        
        if is_first_card:
            prologue_requirement = """
7. **开场白设计**：这是第一张卡片，需要设计一段精彩的开场白，就像剧本杀中NPC的开场介绍一样，用于在交互开始前展示给学生，建立场景氛围和角色第一印象"""
            prologue_output_section = """
# Prologue
[开场白：NPC角色的自我介绍或场景引入，50-80字左右，用于在交互开始前展示给学生]
"""
        
        user_prompt = f"""# 完整剧本

{full_script}

---

# 当前任务

请为【第{stage_index}幕：{stage['title']}】设计A类卡片（NPC角色）的完整提示词。

## 场景信息
- 阶段编号：{stage_index}/{total_stages}
- 场景标题：{stage['title']}
- NPC角色：{stage['role']}
- 场景目标：{stage['task']}
- 关键剧情点：{', '.join(stage['key_points'])}
- 原文参考：{stage['content_excerpt']}
{student_role_hint}

## 设计要求

1. **角色沉浸**：完全沉浸在NPC角色中，像真人一样与学生对话
2. **自然对话**：根据学生的回应自然推进剧情，不要机械地判定对错
3. **开放式交互**：允许学生用多种方式回应，只要合理就推进剧情
4. **适时引导**：只有当学生明显卡住时，才在对话中自然地给予提示
5. **场景切换**：当剧情达到自然转折点时，跳转到：{next_card}
6. **简洁对话**：平台以语音形式沟通，每次回复**控制在50-100字左右**，不要长篇大论{prologue_requirement}

## 输出格式

请按以下结构输出卡片内容：
{prologue_output_section}
# Role
[NPC是谁，背景、性格、说话方式]

# Context
[当前场景的背景，学生扮演什么角色，正在发生什么]

# Interaction
[如何与学生对话，如何根据学生回应推进剧情]

# Transition
[什么情况下触发场景切换]
当剧情自然进展到转折点时，仅输出：**{next_card}**

# Constraints
[角色扮演的限制和注意事项]
- 完全沉浸在角色中
- **每轮只问1-2个问题**，避免连续追问多个问题让学生疲惫
- **严禁任何括号内容**：不要用（）写心理活动、动作描写、旁白等
- 所有对话都应该可以直接朗读，不要有舞台剧式的提示
- **控制对话长度**：每次回复50-100字左右，简洁有力
- 不要机械判定对错

---

请直接输出卡片内容："""

        try:
            return self._call_api(self.system_context, user_prompt)
        except Exception as e:
            raise RuntimeError(f"生成A类卡片失败: {e}")
    
    def _is_same_role(self, current_role: str, next_role: str) -> bool:
        """判断前后角色是否相同（模糊匹配）"""
        if not current_role or not next_role:
            return True  # 如果角色信息缺失，默认视为同一角色
        
        # 提取角色名称的核心部分进行比较
        current_name = current_role.split('，')[0].split(',')[0].strip()
        next_name = next_role.split('，')[0].split(',')[0].strip()
        
        return current_name == next_name
    
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
        is_last_stage = stage_index >= total_stages
        next_card = "结束" if is_last_stage else f"卡片{stage_index + 1}A"
        
        # 判断前后角色是否相同
        current_role = stage.get('role', '')
        next_role = next_stage.get('role', '') if next_stage else ''
        use_narrator = not self._is_same_role(current_role, next_role) and not is_last_stage
        
        next_stage_info = ""
        if next_stage:
            next_stage_info = f"""
## 下一幕预告
- 标题：{next_stage['title']}
- 角色：{next_stage['role']}
- 目标：{next_stage['task']}"""
        
        # 根据是否需要旁白选择不同的prompt
        if use_narrator:
            # 角色不同，需要旁白来衔接
            output_format = """## 输出格式

请按以下结构输出卡片内容：

# Role
[旁白/叙述者的定位，1句话即可]

# Context
[说明本过渡语的使用原则：根据上一环节实际表现，表现好则肯定，表现不足则简要指出，然后衔接角色切换。1-2句话]

# Output
[过渡内容，**控制在50-80字**：体现「根据事实」——可写肯定版/指出不足版两种表述或通用指引，然后说明角色切换、介绍新角色登场]

# Transition
输出完毕后，仅输出：**{next_card}**

# Constraints
- **严禁任何括号内容**
- **控制输出长度**：# Output部分50-80字
- 所有文字都应该可以直接朗读出来""".format(next_card=next_card)
        else:
            # 角色相同，简洁过渡
            output_format = """## 输出格式

请按以下结构输出卡片内容（注意：不需要Role部分，因为角色没有变化）：

# Context
[说明本过渡语的使用原则：根据上一环节实际表现，表现好则肯定，表现不足则简要指出，然后开启下一环节。1句话]

# Output
[简洁的过渡语，**控制在30-80字**：体现「根据事实」——可写肯定版（如肯定其陈述）与指出不足版（如简要指出缺失后）两种表述，或一句通用指引（如「根据上一环节表现予以肯定或简要指出不足后，接下来进入……」）。不要第三人称场景描写]

# Transition
输出完毕后，仅输出：**{next_card}**

# Constraints
- **严禁任何括号内容**
- **严禁第三人称描述或场景叙述**
- **控制输出长度**：# Output部分30-50字
- 所有文字都应该可以直接朗读出来""".format(next_card=next_card)
        
        user_prompt = f"""# 完整剧本

{full_script}

---

# 当前任务

请为【第{stage_index}幕 → 第{stage_index + 1}幕】的过渡设计B类卡片。

## 上一幕信息
- 阶段编号：{stage_index}/{total_stages}
- 场景标题：{stage['title']}
- 场景目标：{stage['task']}
- 关键剧情点：{', '.join(stage['key_points'])}
- 当前角色：{current_role}
{next_stage_info}

## 角色变化情况
{"前后角色不同，需要旁白来衔接角色切换" if use_narrator else "前后角色相同，只需要简洁的功能性过渡，不需要旁白"}

## 设计要求

1. **根据事实进行过渡**：过渡语应根据上一环节**实际对话表现**来写——学生做得好就肯定，做得不好就简要指出问题，然后开启下一环节。不要一律中性或一律表扬，要根据事实；指出不足时也要自然开启下一步。
2. {"**角色切换**：说明上一个角色退场，新角色登场" if use_narrator else "**简洁过渡**：直接衔接下一环节，不需要场景描写"}
3. {"**总结收尾**：这是最后一幕，需要对整个体验做总结" if is_last_stage else "**引入下一幕**：自然引入下一个场景"}

## 重要！严禁括号内容

- **绝对不要使用任何括号**来写动作描写、场景描写、旁白等
- 错误示例：（灯光渐暗）、（转身离开）、（场景切换到...）
- 正确做法：用自然的叙述语言描述

{"" if use_narrator else '''## 重要！禁止第三人称描述

- **不要使用第三人称描述角色**，如"陈新农微微颔首"、"他的目光转向..."
- 因为前后是同一个角色，不需要旁白式的场景描写
- 只需要简洁地说明进入下一环节即可
'''}

{output_format}

---

请直接输出卡片内容："""

        try:
            return self._call_api(self.system_context, user_prompt)
        except Exception as e:
            raise RuntimeError(f"生成B类卡片失败: {e}")
    
    def _create_stage_meta(self, stage: dict) -> str:
        """
        创建阶段元数据块（HTML注释格式，可被 card_injector 解析）
        """
        meta = {
            "stage_name": stage.get("title", ""),
            "description": stage.get("description", ""),
            "interaction_rounds": stage.get("interaction_rounds", 5),
        }
        return f"<!-- STAGE_META: {json.dumps(meta, ensure_ascii=False)} -->\n"
    
    def generate_all_cards(self, stages: list[dict], original_content: str,
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
            # 生成阶段元数据
            stage_meta = self._create_stage_meta(stage)
            
            # 生成A类卡片
            if progress_callback:
                progress_callback(i * 2 - 1, total_stages * 2, 
                                f"正在生成第{i}幕A类卡片（NPC角色）...")
            
            card_a = self.generate_card_a(stage, i, total_stages, original_content)
            all_cards.append(f"# 卡片{i}A\n\n{stage_meta}{card_a}")
            
            # 生成B类卡片
            if progress_callback:
                progress_callback(i * 2, total_stages * 2,
                                f"正在生成第{i}幕B类卡片（场景过渡）...")
            
            next_stage = stages[i] if i < total_stages else None
            card_b = self.generate_card_b(stage, i, total_stages, next_stage, original_content)
            all_cards.append(f"# 卡片{i}B\n\n{card_b}")
        
        # 用分隔线连接所有卡片
        return "\n\n---\n\n".join(all_cards)
