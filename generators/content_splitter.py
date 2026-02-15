"""
内容分割器
调用DeepSeek API分析剧本，将其划分为多个场景/幕
适用于沉浸式角色扮演教学平台（类似"课程版剧本杀"）
支持按内容哈希缓存分析结果（内存 + 可选磁盘），避免重复请求。
"""
import hashlib
import json
import os
import re
from typing import Optional

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    DOUBAO_API_KEY, DOUBAO_BASE_URL, DOUBAO_MODEL,
    DEFAULT_MODEL_TYPE, MAX_TOKENS, TEMPERATURE
)

# 分析结果缓存：同一剧本内容只请求一次 API，最多保留条目数
_ANALYZE_CACHE: dict[str, dict] = {}
_ANALYZE_CACHE_MAX = 32

# 单次分析送入模型的剧本最大字符数，避免超出上下文或超时（约 5 万字符）
ANALYZE_CONTENT_MAX_CHARS = 50000

# 磁盘缓存目录（项目根下 .cache/content_splitter），重启后仍可命中
def _disk_cache_dir() -> Optional[str]:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(root, ".cache", "content_splitter")
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except OSError:
        return None


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

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        初始化内容分割器。可与工作区 LLM 配置统一（api_key / base_url / model）。
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("请先安装openai库: pip install openai")
        self.api_key = api_key or (DOUBAO_API_KEY if DEFAULT_MODEL_TYPE == "doubao" else DEEPSEEK_API_KEY)
        if not self.api_key:
            raise ValueError("未提供API密钥，请在 Web 设置中填写或设置 .env 中的 DEEPSEEK_API_KEY / LLM_API_KEY")
        self.base_url = (base_url or "").strip() or (DOUBAO_BASE_URL if DEFAULT_MODEL_TYPE == "doubao" else DEEPSEEK_BASE_URL)
        self.model = (model or "").strip() or (DOUBAO_MODEL if DEFAULT_MODEL_TYPE == "doubao" else DEEPSEEK_MODEL)
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
    
    def analyze(self, content: str, use_cache: bool = True) -> dict:
        """
        分析剧本内容，返回场景分割方案。
        相同内容会使用缓存结果，避免重复 API 调用。

        Args:
            content: 剧本的文本内容
            use_cache: 是否使用内存缓存（默认 True）

        Returns:
            包含stages列表的字典，每个stage包含id, title, role, student_role, task, key_points, content_excerpt等
        """
        # 超长内容截断，避免 API 超时或超出上下文
        truncated_note = ""
        if len(content) > ANALYZE_CONTENT_MAX_CHARS:
            content = content[:ANALYZE_CONTENT_MAX_CHARS] + "\n\n[以下内容因篇幅过长已省略，仅对以上部分进行分幕分析。建议将文档拆成多个较小文件或只分析前半部分。]"
            truncated_note = f"（已截断，原长超过 {ANALYZE_CONTENT_MAX_CHARS} 字）"

        key = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if use_cache:
            if key in _ANALYZE_CACHE:
                return _ANALYZE_CACHE[key]
            # 磁盘缓存：重启后相同剧本不再请求 API
            cache_dir = _disk_cache_dir()
            if cache_dir:
                cache_file = os.path.join(cache_dir, f"{key}.json")
                try:
                    if os.path.isfile(cache_file):
                        with open(cache_file, "r", encoding="utf-8") as f:
                            result = json.load(f)
                        if "stages" in result:
                            if len(_ANALYZE_CACHE) >= _ANALYZE_CACHE_MAX:
                                first = next(iter(_ANALYZE_CACHE))
                                del _ANALYZE_CACHE[first]
                            _ANALYZE_CACHE[key] = result
                            return result
                except (OSError, json.JSONDecodeError):
                    pass
            if len(_ANALYZE_CACHE) >= _ANALYZE_CACHE_MAX:
                first = next(iter(_ANALYZE_CACHE))
                del _ANALYZE_CACHE[first]

        prompt = self.SPLIT_PROMPT.format(content=content)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
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
            if truncated_note:
                result["_truncated_note"] = truncated_note

            if use_cache:
                _ANALYZE_CACHE[key] = result
                cache_dir = _disk_cache_dir()
                if cache_dir:
                    cache_file = os.path.join(cache_dir, f"{key}.json")
                    try:
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump(result, f, ensure_ascii=False, indent=2)
                    except OSError:
                        pass
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
