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
6. **简洁对话**：平台以语音形式沟通，每次回复**控制在50-100字左右**，不要长篇大论

## 输出格式

请按以下结构输出卡片内容：

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
    
    def generate_card_b(self, stage: dict, stage_index: int, total_stages: int,
                        next_stage: Optional[dict], full_script: str) -> str:
        """
        生成B类卡片（场景过渡/旁白卡片）
        
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
        
        next_stage_info = ""
        if next_stage:
            next_stage_info = f"""
## 下一幕预告
- 标题：{next_stage['title']}
- 角色：{next_stage['role']}
- 目标：{next_stage['task']}"""
        
        user_prompt = f"""# 完整剧本

{full_script}

---

# 当前任务

请为【第{stage_index}幕 → 第{stage_index + 1}幕】的过渡设计B类卡片（场景过渡/旁白）。

## 上一幕信息
- 阶段编号：{stage_index}/{total_stages}
- 场景标题：{stage['title']}
- 场景目标：{stage['task']}
- 关键剧情点：{', '.join(stage['key_points'])}
{next_stage_info}

## 设计要求

1. **承上启下**：自然地连接上一幕和下一幕
2. **场景描述**：描述场景变化、时间流逝、氛围转换
3. **剧情铺垫**：为下一幕做适当铺垫，引起学生兴趣
4. {"**总结收尾**：这是最后一幕，需要对整个体验做总结" if is_last_stage else "**引入下一幕**：自然引入下一个场景和角色"}

## 重要！严禁括号内容

- **绝对不要使用任何括号**来写动作描写、场景描写、旁白等
- 错误示例：（灯光渐暗）、（转身离开）、（场景切换到...）
- 正确做法：用自然的叙述语言描述，所有内容都应该可以直接朗读
- 原因：平台只有一个语音通道，括号内容会非常出戏

## 重要！控制输出长度

- 平台以**语音形式**与学生沟通，过长的文本会让体验变差
- # Output 部分的文字**控制在50-80字左右**（约20-30秒朗读）
- 简洁有力，点到为止，不要铺陈太多

## 输出格式

请按以下结构输出卡片内容：

# Role
[旁白/叙述者的定位，1-2句话即可]

# Context
[上一幕发生了什么，简要说明]

# Output
[具体的过渡内容，**控制在50-80字**，简洁有力：
- 简短回顾上一幕（1句话）
- 自然引入下一幕（1-2句话）]

# Transition
输出完毕后，仅输出：**{next_card}**

# Constraints
- **严禁任何括号内容**（心理、动作、场景描写都不要用括号）
- **控制输出长度**：# Output部分50-80字左右
- 所有文字都应该可以直接朗读出来

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
