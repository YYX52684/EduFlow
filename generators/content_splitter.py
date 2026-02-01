"""
内容分割器
调用DeepSeek API分析剧本，将其划分为多个场景/幕
适用于沉浸式角色扮演教学平台（类似"课程版剧本杀"）
"""
import json
import re
from typing import Optional

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    MAX_TOKENS, TEMPERATURE
)


class ContentSplitter:
    """
    内容分割器类
    负责分析剧本并将其划分为独立的场景/幕
    """
    
    SPLIT_PROMPT = """你是一个剧本分析专家，擅长为沉浸式角色扮演体验设计场景结构。

请分析以下剧本，将其划分为多个**场景/幕**。这是一个类似"剧本杀"的沉浸式学习体验，学生会与AI扮演的角色对话。

请严格按照以下JSON格式返回分析结果（不要添加任何其他说明文字，不要使用markdown代码块）：

{{
  "stages": [
    {{
      "id": 1,
      "title": "场景标题（简短描述，不超过15字）",
      "description": "场景详细描述（这一幕要达成什么体验/学习目标，2-3句话）",
      "interaction_rounds": 5,
      "role": "NPC角色（学生将与谁对话，如：渔父、贾谊、患者张先生等）",
      "student_role": "学生扮演的角色（如果有明确设定，如：屈原、医生等）",
      "task": "场景目标（这一幕的剧情要推进到什么程度，或学生要完成什么）",
      "key_points": ["剧情关键点1", "知识/情感要点2", "核心对话主题3"],
      "content_excerpt": "该场景对应的原文关键内容或对话摘要"
    }}
  ]
}}

字段说明：
- title: 场景名称，用于显示在节点上
- description: 详细描述，解释这一幕的体验目标
- interaction_rounds: 建议的对话轮次（1-10），根据场景复杂度判断：
  - 简短互动场景：1-3轮
  - 中等深度场景：4-6轮
  - 深度探讨/多话题场景：7-10轮
- role: NPC角色，即AI扮演的角色
- student_role: 学生扮演的角色（如果剧本中有明确设定）
- task: 场景目标，描述剧情要推进的方向
- key_points: 这一幕的核心内容，可以是知识点、情感要点、对话主题等
- content_excerpt: 原文中与该场景相关的关键内容

划分原则：
1. 每个场景应该有相对完整的剧情单元
2. 场景之间应该有自然的剧情递进
3. 每个场景的体量适中，适合一组NPC对话
4. 保留原文中的角色关系和情境氛围
5. **不要把这当成考试来划分**，而是当成一个沉浸式体验来设计

以下是需要分析的剧本内容：

---
{content}
---

请直接返回JSON格式的分析结果（不要使用```json标记）："""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化内容分割器
        
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
    
    def analyze(self, content: str) -> dict:
        """
        分析剧本内容，返回场景分割方案
        
        Args:
            content: 剧本的文本内容
            
        Returns:
            包含stages列表的字典，每个stage包含id, title, role, student_role, task, key_points, content_excerpt等
        """
        prompt = self.SPLIT_PROMPT.format(content=content)
        
        try:
            response = self.client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # 尝试提取JSON内容
            result = self._extract_json(response_text)
            
            # 验证结果格式
            if "stages" not in result:
                raise ValueError("API返回的结果缺少stages字段")
            
            return result
            
        except Exception as e:
            if "api" in str(e).lower() or "request" in str(e).lower():
                raise RuntimeError(f"API调用失败: {e}")
            raise
    
    def _extract_json(self, text: str) -> dict:
        """
        从文本中提取JSON内容
        
        Args:
            text: 可能包含JSON的文本
            
        Returns:
            解析后的字典
        """
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 尝试移除 markdown 代码块标记 (```json ... ``` 或 ``` ... ```)
        code_block_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
        match = re.search(code_block_pattern, text, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        # 尝试找到JSON块
        start_idx = text.find('{')
        if start_idx == -1:
            raise ValueError(f"未找到JSON内容。API返回: {text[:500]}...")
        
        end_idx = text.rfind('}')
        if end_idx == -1:
            raise ValueError(f"未找到JSON结束标记。API返回: {text[:500]}...")
        
        json_str = text[start_idx:end_idx + 1]
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON解析失败: {e}。提取的内容: {json_str[:500]}...")
    
    def preview(self, content: str) -> None:
        """
        预览分析结果（不生成卡片，仅显示分割方案）
        
        Args:
            content: 剧本的文本内容
        """
        result = self.analyze(content)
        
        print("\n" + "=" * 60)
        print("剧本分析结果")
        print("=" * 60)
        print(f"\n共识别出 {len(result['stages'])} 个场景/幕：\n")
        
        for stage in result['stages']:
            print(f"【第{stage['id']}幕】{stage['title']}")
            print(f"  描述: {stage.get('description', '无')}")
            print(f"  对话轮次: {stage.get('interaction_rounds', 5)}")
            print(f"  NPC角色: {stage['role']}")
            if stage.get('student_role'):
                print(f"  学生扮演: {stage['student_role']}")
            print(f"  场景目标: {stage['task']}")
            print(f"  关键点: {', '.join(stage['key_points'])}")
            excerpt = stage.get('content_excerpt', '')
            if excerpt:
                print(f"  内容摘要: {excerpt[:100]}...")
            print()
        
        print("=" * 60)
