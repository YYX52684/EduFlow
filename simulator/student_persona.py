"""
学生人设管理
支持预设人设和自定义剧本角色人设

预设人设类型：
- excellent: 优秀学生 - 理解力强、回答准确、主动深入
- average: 普通学生 - 正常水平、偶有疑惑  
- struggling: 较弱学生 - 理解困难、需要引导

自定义人设：
- 支持YAML文件定义角色背景、性格、目标
- 类似剧本杀角色，有特定的行动目标和限制

智能生成：
- 使用Claude Sonnet根据原始教学材料自动生成推荐角色配置
"""

import os
import json
import yaml
import requests
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field


@dataclass
class StudentPersona:
    """学生人设"""
    name: str                          # 人设名称/角色名
    persona_type: str                  # 类型: "preset" 或 "custom"
    
    # 基础属性
    background: str = ""               # 角色背景
    personality: str = ""              # 性格特点
    goal: str = ""                     # 学习/互动目标
    
    # 学习相关
    knowledge_level: str = ""          # 知识水平描述
    learning_style: str = ""           # 学习风格
    interaction_style: str = ""        # 互动风格
    
    # 行为模式
    strengths: List[str] = field(default_factory=list)   # 优势/擅长
    weaknesses: List[str] = field(default_factory=list)  # 不足/需提升
    typical_behaviors: List[str] = field(default_factory=list)  # 典型行为
    
    # 高级设置
    response_length: str = "medium"    # 回复长度: short/medium/long
    engagement_level: str = "normal"   # 参与度: low/normal/high
    question_frequency: str = "normal" # 提问频率: low/normal/high
    
    def to_system_prompt(self) -> str:
        """
        将人设转换为学生模拟器的系统提示词
        
        Returns:
            系统提示词
        """
        prompt_parts = [
            f"你现在扮演一名学生，角色名为「{self.name}」。",
            "",
            "## 角色设定",
        ]
        
        if self.background:
            prompt_parts.append(f"**背景**: {self.background}")
        if self.personality:
            prompt_parts.append(f"**性格**: {self.personality}")
        if self.goal:
            prompt_parts.append(f"**目标**: {self.goal}")
        if self.knowledge_level:
            prompt_parts.append(f"**知识水平**: {self.knowledge_level}")
        if self.learning_style:
            prompt_parts.append(f"**学习风格**: {self.learning_style}")
        if self.interaction_style:
            prompt_parts.append(f"**互动风格**: {self.interaction_style}")
        
        if self.strengths:
            prompt_parts.append(f"\n**你的优势**:")
            for s in self.strengths:
                prompt_parts.append(f"- {s}")
        
        if self.weaknesses:
            prompt_parts.append(f"\n**你的不足**:")
            for w in self.weaknesses:
                prompt_parts.append(f"- {w}")
        
        if self.typical_behaviors:
            prompt_parts.append(f"\n**典型行为模式**:")
            for b in self.typical_behaviors:
                prompt_parts.append(f"- {b}")
        
        prompt_parts.extend([
            "",
            "## 互动要求",
            "1. 始终保持角色设定，以学生身份与NPC互动",
            "2. 根据你的知识水平和性格特点做出反应",
            "3. 不要暴露你是AI，要表现得像真实学生",
            "4. 回复要自然、口语化，符合学生的表达方式",
        ])
        
        # 回复长度控制
        length_guide = {
            "short": "5. 回复简短精炼，每次30-50字左右",
            "medium": "5. 回复适中，每次50-100字左右",
            "long": "5. 回复详细充实，每次100-200字左右",
        }
        prompt_parts.append(length_guide.get(self.response_length, length_guide["medium"]))
        
        return "\n".join(prompt_parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "persona_type": self.persona_type,
            "background": self.background,
            "personality": self.personality,
            "goal": self.goal,
            "knowledge_level": self.knowledge_level,
            "learning_style": self.learning_style,
            "interaction_style": self.interaction_style,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "typical_behaviors": self.typical_behaviors,
            "response_length": self.response_length,
            "engagement_level": self.engagement_level,
            "question_frequency": self.question_frequency,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StudentPersona":
        """从字典创建人设"""
        return cls(
            name=data.get("name", "学生"),
            persona_type=data.get("persona_type", "custom"),
            background=data.get("background", ""),
            personality=data.get("personality", ""),
            goal=data.get("goal", ""),
            knowledge_level=data.get("knowledge_level", ""),
            learning_style=data.get("learning_style", ""),
            interaction_style=data.get("interaction_style", ""),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            typical_behaviors=data.get("typical_behaviors", []),
            response_length=data.get("response_length", "medium"),
            engagement_level=data.get("engagement_level", "normal"),
            question_frequency=data.get("question_frequency", "normal"),
        )


# ========== 预设人设定义 ==========

PRESET_PERSONAS = {
    "excellent": StudentPersona(
        name="优秀学生",
        persona_type="preset",
        background="学业成绩优异，知识面广，学习态度端正",
        personality="认真专注、好学上进、善于思考、表达清晰",
        goal="深入理解知识，追求卓越表现",
        knowledge_level="扎实的基础知识，对相关领域有较深入了解",
        learning_style="主动学习，善于提问，能举一反三",
        interaction_style="积极参与，回答准确，能主动深入探讨",
        strengths=[
            "理解能力强，能快速把握重点",
            "回答问题逻辑清晰、条理分明",
            "能主动联系已学知识进行拓展",
            "善于发现问题并提出有深度的疑问",
        ],
        weaknesses=[
            "偶尔过于追求完美",
            "有时会钻牛角尖",
        ],
        typical_behaviors=[
            "听到问题后会先思考，然后给出结构化的回答",
            "能准确回应NPC的提问，并补充相关细节",
            "会主动请求进一步解释或深入讨论",
            "在不确定时会谨慎表达，而非胡乱猜测",
        ],
        response_length="medium",
        engagement_level="high",
        question_frequency="high",
    ),
    
    "average": StudentPersona(
        name="普通学生",
        persona_type="preset",
        background="普通大学生，学习态度一般，基础知识掌握尚可",
        personality="随和、稍显被动、偶尔走神",
        goal="完成学习任务，通过考核",
        knowledge_level="基础知识掌握一般，部分概念理解不够深入",
        learning_style="跟随式学习，需要引导和提示",
        interaction_style="正常参与，有时需要鼓励才会主动发言",
        strengths=[
            "能理解基本概念和简单问题",
            "态度友好，愿意配合",
            "在提示下能给出正确回答",
        ],
        weaknesses=[
            "对复杂问题理解困难",
            "表达有时不够清晰完整",
            "需要NPC引导才能深入",
            "注意力容易分散",
        ],
        typical_behaviors=[
            "回答问题基本正确，但可能不够完整",
            "遇到难题时会表示困惑或请求提示",
            "有时会回答得比较简短",
            "在NPC引导下能逐步给出更好的答案",
        ],
        response_length="medium",
        engagement_level="normal",
        question_frequency="normal",
    ),
    
    "struggling": StudentPersona(
        name="较弱学生",
        persona_type="preset",
        background="基础较薄弱，学习动力不足，经常感到困难",
        personality="内向、缺乏自信、容易紧张",
        goal="希望能跟上进度，但经常感到力不从心",
        knowledge_level="基础知识掌握不牢，概念容易混淆",
        learning_style="被动学习，依赖老师讲解，缺乏自主思考",
        interaction_style="回答问题犹豫、不够自信，容易跑偏",
        strengths=[
            "态度诚恳，愿意学习",
            "在足够耐心的引导下能有所进步",
        ],
        weaknesses=[
            "基础概念理解不清",
            "表达混乱，容易答非所问",
            "缺乏举一反三的能力",
            "容易紧张导致表现失常",
            "注意力难以长时间集中",
        ],
        typical_behaviors=[
            "回答时会犹豫、不确定，经常使用\"可能\"、\"大概\"",
            "容易偏离问题主题",
            "需要NPC多次引导才能理解要点",
            "有时会给出错误或不相关的答案",
            "在被纠正后能接受，但可能很快又犯类似错误",
        ],
        response_length="short",
        engagement_level="low",
        question_frequency="low",
    ),
}


class PersonaManager:
    """人设管理器"""
    
    def __init__(self, config_dir: str = None):
        """
        初始化人设管理器
        
        Args:
            config_dir: 配置目录路径，默认为项目根目录下的simulator_config
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # 默认使用项目根目录下的simulator_config
            project_root = Path(__file__).parent.parent
            self.config_dir = project_root / "simulator_config"
        
        self.presets_dir = self.config_dir / "presets"
        self.custom_dir = self.config_dir / "custom"
    
    def get_persona(self, persona_id: str) -> StudentPersona:
        """
        获取人设
        
        Args:
            persona_id: 人设标识符，可以是：
                - 预设名称: "excellent", "average", "struggling"
                - 自定义文件路径: "custom/entrepreneur.yaml"
                
        Returns:
            StudentPersona实例
        """
        # 检查是否是预设人设
        if persona_id in PRESET_PERSONAS:
            return PRESET_PERSONAS[persona_id]
        
        # 尝试从文件加载
        return self.load_from_file(persona_id)
    
    def load_from_file(self, file_path: str) -> StudentPersona:
        """
        从YAML文件加载人设
        
        Args:
            file_path: 相对于config_dir的路径，或绝对路径
            
        Returns:
            StudentPersona实例
        """
        # 处理路径
        if os.path.isabs(file_path):
            path = Path(file_path)
        else:
            path = self.config_dir / file_path
        
        # 确保有.yaml扩展名
        if not path.suffix:
            path = path.with_suffix('.yaml')
        
        if not path.exists():
            # 尝试在custom目录下查找
            alt_path = self.custom_dir / path.name
            if alt_path.exists():
                path = alt_path
            else:
                raise FileNotFoundError(f"人设文件不存在: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        data["persona_type"] = "custom"
        return StudentPersona.from_dict(data)
    
    def save_to_file(self, persona: StudentPersona, file_path: str):
        """
        保存人设到YAML文件
        
        Args:
            persona: 人设对象
            file_path: 保存路径
        """
        path = self.custom_dir / file_path
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(persona.to_dict(), f, allow_unicode=True, default_flow_style=False)
    
    def list_presets(self) -> List[str]:
        """列出所有预设人设"""
        return list(PRESET_PERSONAS.keys())
    
    def list_custom(self) -> List[str]:
        """列出所有自定义人设"""
        if not self.custom_dir.exists():
            return []
        return [f.stem for f in self.custom_dir.glob("*.yaml")]
    
    def create_custom_persona(
        self,
        name: str,
        background: str,
        personality: str,
        goal: str,
        **kwargs
    ) -> StudentPersona:
        """
        创建自定义人设
        
        Args:
            name: 角色名
            background: 背景描述
            personality: 性格特点
            goal: 目标
            **kwargs: 其他属性
            
        Returns:
            新创建的人设
        """
        return StudentPersona(
            name=name,
            persona_type="custom",
            background=background,
            personality=personality,
            goal=goal,
            **kwargs
        )
    
    def ensure_config_dirs(self):
        """确保配置目录存在"""
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        self.custom_dir.mkdir(parents=True, exist_ok=True)
    
    def export_presets(self):
        """导出预设人设到YAML文件"""
        self.ensure_config_dirs()
        for name, persona in PRESET_PERSONAS.items():
            path = self.presets_dir / f"{name}.yaml"
            with open(path, 'w', encoding='utf-8') as f:
                yaml.dump(persona.to_dict(), f, allow_unicode=True, default_flow_style=False)


class PersonaGenerator:
    """
    角色人设生成器
    使用Claude Sonnet根据原始教学材料自动生成推荐的学生角色配置
    """
    
    # 默认配置
    DEFAULT_API_URL = "http://llm-service.polymas.com/api/openai/v1/chat/completions"
    DEFAULT_MODEL = "claude-sonnet-4-5-20250514"
    DEFAULT_SERVICE_CODE = "SI_Ability"
    
    def __init__(self, config: dict = None):
        """
        初始化角色生成器
        
        Args:
            config: 配置字典
        """
        config = config or {}
        
        self.api_url = config.get("api_url", self.DEFAULT_API_URL)
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", self.DEFAULT_MODEL)
        self.service_code = config.get("service_code", self.DEFAULT_SERVICE_CODE)
    
    def generate_from_material(
        self,
        material_content: str,
        num_personas: int = 3,
        include_preset_types: bool = True,
    ) -> List[StudentPersona]:
        """
        根据原始教学材料生成推荐的角色配置
        
        Args:
            material_content: 原始教学材料内容（剧本、课程大纲等）
            num_personas: 生成的角色数量
            include_preset_types: 是否包含预设类型（优秀/普通/较弱）的变体
            
        Returns:
            生成的角色人设列表
        """
        prompt = self._build_generation_prompt(
            material_content, 
            num_personas, 
            include_preset_types
        )
        
        response = self._call_llm(prompt)
        personas = self._parse_response(response)
        
        return personas
    
    def generate_single_persona(
        self,
        material_content: str,
        persona_type: str = "custom",
        additional_requirements: str = "",
    ) -> StudentPersona:
        """
        生成单个特定类型的角色
        
        Args:
            material_content: 原始教学材料内容
            persona_type: 角色类型 (excellent/average/struggling/custom)
            additional_requirements: 额外要求描述
            
        Returns:
            生成的角色人设
        """
        prompt = self._build_single_persona_prompt(
            material_content,
            persona_type,
            additional_requirements
        )
        
        response = self._call_llm(prompt)
        personas = self._parse_response(response)
        
        if personas:
            return personas[0]
        raise ValueError("无法生成角色配置")
    
    def _build_generation_prompt(
        self,
        material_content: str,
        num_personas: int,
        include_preset_types: bool,
    ) -> str:
        """构建角色生成提示词"""
        
        type_guidance = ""
        if include_preset_types:
            type_guidance = """
请确保生成的角色覆盖不同能力水平：
1. 至少一个"优秀型"角色：理解力强、回答准确、主动深入
2. 至少一个"普通型"角色：正常水平、偶有疑惑
3. 至少一个"挑战型"角色：理解困难或有特殊行为模式（如容易跑题、喜欢质疑等）
"""
        
        return f"""你是一名专业的教学设计专家。请根据以下教学材料，生成{num_personas}个适合该教学场景的学生角色配置。

## 教学材料
{material_content[:8000]}

{type_guidance}

## 输出要求
请为每个角色生成完整的配置，以JSON数组格式返回。每个角色包含以下字段：

```json
[
  {{
    "name": "角色名称（如：创业者小王、好奇学生小李）",
    "background": "角色背景描述（100字以内）",
    "personality": "性格特点（如：认真专注、善于思考）",
    "goal": "该角色在本场景中的目标",
    "knowledge_level": "知识水平描述",
    "learning_style": "学习风格",
    "interaction_style": "互动风格",
    "strengths": ["优势1", "优势2"],
    "weaknesses": ["不足1", "不足2"],
    "typical_behaviors": ["典型行为1", "典型行为2", "典型行为3"],
    "response_length": "short/medium/long",
    "engagement_level": "low/normal/high",
    "question_frequency": "low/normal/high"
  }}
]
```

## 设计原则
1. 角色要符合教学材料的场景和主题
2. 每个角色要有独特的特点，便于测试不同的教学情境
3. 背景描述要具体，与教学内容相关
4. 典型行为要能体现角色特点，便于模拟器执行

请直接返回JSON数组，不要添加其他说明。
"""
    
    def _build_single_persona_prompt(
        self,
        material_content: str,
        persona_type: str,
        additional_requirements: str,
    ) -> str:
        """构建单个角色生成提示词"""
        
        type_descriptions = {
            "excellent": "优秀学生：理解力强、回答准确、主动深入思考、善于提问",
            "average": "普通学生：正常水平、偶有疑惑、需要适当引导",
            "struggling": "较弱学生：理解困难、需要更多引导、容易跑偏",
            "custom": "自定义角色：根据材料特点设计独特的角色",
        }
        
        type_desc = type_descriptions.get(persona_type, type_descriptions["custom"])
        
        extra = ""
        if additional_requirements:
            extra = f"\n## 额外要求\n{additional_requirements}"
        
        return f"""你是一名专业的教学设计专家。请根据以下教学材料，生成1个适合该教学场景的学生角色配置。

## 角色类型
{type_desc}

## 教学材料
{material_content[:8000]}
{extra}

## 输出要求
请生成完整的角色配置，以JSON数组格式返回（只包含1个角色）：

```json
[
  {{
    "name": "角色名称",
    "background": "角色背景描述",
    "personality": "性格特点",
    "goal": "该角色在本场景中的目标",
    "knowledge_level": "知识水平描述",
    "learning_style": "学习风格",
    "interaction_style": "互动风格",
    "strengths": ["优势1", "优势2"],
    "weaknesses": ["不足1", "不足2"],
    "typical_behaviors": ["典型行为1", "典型行为2", "典型行为3"],
    "response_length": "short/medium/long",
    "engagement_level": "low/normal/high",
    "question_frequency": "low/normal/high"
  }}
]
```

请直接返回JSON数组，不要添加其他说明。
"""
    
    def _call_llm(self, prompt: str) -> str:
        """调用LLM API"""
        headers = {
            "Content-Type": "application/json",
        }
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.service_code:
            headers["serviceCode"] = self.service_code
        
        messages = [
            {
                "role": "system",
                "content": "你是一名专业的教学设计专家，擅长根据教学材料设计学生角色。请严格按照JSON格式返回结果。"
            },
            {"role": "user", "content": prompt}
        ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 4000,
            "temperature": 0.7,
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except Exception as e:
            raise RuntimeError(f"LLM API调用失败: {e}")
    
    def _parse_response(self, response: str) -> List[StudentPersona]:
        """解析LLM响应"""
        import re
        
        # 尝试提取JSON数组
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 尝试直接解析
            json_str = response.strip()
            # 如果以[开头，尝试找到匹配的]
            if json_str.startswith('['):
                bracket_count = 0
                end_pos = 0
                for i, char in enumerate(json_str):
                    if char == '[':
                        bracket_count += 1
                    elif char == ']':
                        bracket_count -= 1
                        if bracket_count == 0:
                            end_pos = i + 1
                            break
                if end_pos > 0:
                    json_str = json_str[:end_pos]
        
        try:
            data_list = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"无法解析LLM返回的JSON: {e}\n原始内容: {response[:500]}")
        
        personas = []
        for data in data_list:
            data["persona_type"] = "generated"
            persona = StudentPersona.from_dict(data)
            personas.append(persona)
        
        return personas
    
    def save_personas(
        self,
        personas: List[StudentPersona],
        output_dir: str = None,
        prefix: str = "generated",
    ) -> List[str]:
        """
        保存生成的角色配置到YAML文件
        
        Args:
            personas: 角色列表
            output_dir: 输出目录
            prefix: 文件名前缀
            
        Returns:
            保存的文件路径列表
        """
        if output_dir is None:
            project_root = Path(__file__).parent.parent
            output_dir = project_root / "simulator_config" / "custom"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        saved_paths = []
        for i, persona in enumerate(personas):
            # 生成文件名（使用角色名的拼音或简化版本）
            safe_name = persona.name.replace(" ", "_").replace("/", "_")[:20]
            filename = f"{prefix}_{i+1}_{safe_name}.yaml"
            filepath = output_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                yaml.dump(persona.to_dict(), f, allow_unicode=True, default_flow_style=False)
            
            saved_paths.append(str(filepath))
        
        return saved_paths


class PersonaGeneratorFactory:
    """角色生成器工厂"""
    
    @staticmethod
    def create_from_env() -> PersonaGenerator:
        """从环境变量创建角色生成器"""
        from dotenv import load_dotenv
        load_dotenv()
        
        config = {
            "api_url": os.getenv("SIMULATOR_API_URL", PersonaGenerator.DEFAULT_API_URL),
            "api_key": os.getenv("SIMULATOR_API_KEY", ""),
            "model": os.getenv("SIMULATOR_MODEL", PersonaGenerator.DEFAULT_MODEL),
            "service_code": os.getenv("SIMULATOR_SERVICE_CODE", PersonaGenerator.DEFAULT_SERVICE_CODE),
        }
        
        return PersonaGenerator(config)
