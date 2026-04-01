"""
LLM NPC模拟器
使用A类卡片的prompt作为系统指令，模拟NPC对话

模型配置：默认使用 DeepSeek，与卡片生成一致；可通过 NPC_* / SIMULATOR_* 环境变量覆盖。
"""

import os
import json
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from .llm_client import get_simulator_default_config, call_chat_completion


@dataclass
class NPCMessage:
    """NPC消息"""
    role: str           # "npc" 或 "student"
    content: str        # 消息内容
    metadata: dict = field(default_factory=dict)  # 附加元数据


class LLMNPC:
    """LLM NPC模拟器"""
    
    # 默认配置（DeepSeek）；可通过环境变量 NPC_* / SIMULATOR_* 覆盖
    DEFAULT_API_URL = None  # 运行时从 config 取
    DEFAULT_MODEL = None
    DEFAULT_SERVICE_CODE = ""
    
    def __init__(self, card_prompt: str, config: dict = None):
        """
        初始化NPC模拟器
        
        Args:
            card_prompt: A类卡片的完整prompt（系统指令）
            config: 配置字典，包含：
                - api_url: API地址
                - api_key: API密钥
                - model: 模型名称
                - service_code: 服务代码
                - max_tokens: 最大token数
                - temperature: 温度参数
        """
        config = config or {}
        defaults = get_simulator_default_config()
        self.system_prompt = card_prompt
        self.api_url = config.get("api_url", defaults["api_url"])
        self.api_key = config.get("api_key", defaults["api_key"])
        self.model = config.get("model", defaults["model"])
        self.service_code = config.get("service_code", self.DEFAULT_SERVICE_CODE)
        self.max_tokens = config.get("max_tokens", 400)  # 约 250 字内
        self.temperature = config.get("temperature", 0.7)
        
        # 对话历史
        self.history: List[NPCMessage] = []
        
        # 跳转检测
        self._transition_pattern = re.compile(r'\*\*卡片\d+[AB]\*\*|卡片\d+[AB]')

        # 仅清洗“括号内动作/神态/旁白式描写”，不要一刀切禁止所有括号。
        self._paren_stage_direction_pattern = re.compile(r"[（(](.*?)[)）]", flags=re.DOTALL)
        self._paren_forbidden_keywords = (
            # 明确的声音/语气/颤动类
            "清了清嗓子",
            "清嗓子",
            "声音",
            "发颤",
            "颤",
            "颤抖",
            "呼吸",
            "吸了口气",
            "呼出",
            # 神态/动作类（常见“括号式舞台提示”）
            "微笑",
            "笑着",
            "点头",
            "摇头",
            "看向",
            "注视",
            "凝视",
            "轻声",
            "低声",
            "停顿",
            "叹气",
            "叹息",
            "转身",
            "转过身",
            "起身",
            "坐下",
            "站起",
            "伸手",
            "握",
            "攥",
            "抓",
            "拍",
            "摸",
            "擦",
            "摩挲",
            "摩擦",
            "打断",
        )

    def _strip_paren_action_and_stage_directions(self, text: str) -> str:
        """移除“括号内动作/神态/旁白式描写”；其余括号内容尽量保留。"""
        if not text:
            return text

        def _maybe_strip(match: re.Match) -> str:
            inner = (match.group(1) or "").strip()
            if not inner:
                return ""
            if any(k in inner for k in self._paren_forbidden_keywords):
                return ""
            return match.group(0)

        return self._paren_stage_direction_pattern.sub(_maybe_strip, text)
    
    def respond(self, student_message: str, context: Optional[List[dict]] = None) -> str:
        """
        根据学生输入生成NPC回复
        
        Args:
            student_message: 学生的消息
            context: 额外的上下文（可选）
            
        Returns:
            NPC的回复
        """
        # 角色约束：NPC 做讲解/提问/点评；控制单轮长度；禁止括号出戏；只输出台词不输出动作描写
        role_fix = (
            "\n\n【角色约束】你是 NPC，对方是剧情中的角色（由当前卡片的 Context 设定）。"
            "你的每条回复可以是讲解、提问、点评或引导，但不要替对方陈述思路、答案或设计方案。"
            "单条回复控制在 200 字以内；如果内容会重复，就先删减重复点。"
            "严禁在括号里写动作/神态/旁白式描写；如果括号只是纯术语或补充说明，可适当保留，保持沉浸、不出戏。"
            "回复时只输出角色台词（讲解/提问/点评/引导），不要输出动作或神态描写（如「你微笑着说道」「你看向学生」），否则会破坏沉浸感。"
            "教学策略：当学生给出建议/回答后，你必须追问至少一个开放式问题（如“为什么/怎么做/具体步骤/会遇到什么困难/如何应对/能否举个例子”），避免只做情绪性认可。"
            "追问节奏：每轮只追问一个核心点，确保信息密度但不过长。"
            "去重：避免频繁使用同一种固定句式/连接词（如“对了”“真……真”“以前在村里”等）；避免多轮重复提及同一具体人物名或同一教学细节。若必须引用例子，换一种表述或用泛称。"
        )
        system_content = (self.system_prompt or "").strip() + role_fix
        messages = [
            {"role": "system", "content": system_content}
        ]
        
        # 添加历史对话
        for msg in self.history:
            role = "assistant" if msg.role == "npc" else "user"
            messages.append({"role": role, "content": msg.content})
        
        # 添加当前学生消息
        messages.append({"role": "user", "content": student_message})
        
        # 调用API
        response = self._call_llm(messages)
        
        # 记录历史
        self.history.append(NPCMessage(role="student", content=student_message))
        self.history.append(NPCMessage(role="npc", content=response))
        
        return response
    
    def send_prologue(self, prologue: str) -> str:
        """
        发送开场白
        
        Args:
            prologue: 开场白内容
            
        Returns:
            开场白
        """
        # 开场白直接作为NPC的第一条消息
        self.history.append(NPCMessage(role="npc", content=prologue))
        return prologue
    
    def check_transition(self, response: str) -> Optional[str]:
        """
        检查回复中是否包含跳转指令
        
        Args:
            response: NPC的回复
            
        Returns:
            跳转目标（如"卡片2A"）或None
        """
        match = self._transition_pattern.search(response)
        if match:
            # 提取跳转目标，移除markdown标记
            target = match.group(0).replace("**", "")
            return target
        return None
    
    def get_clean_response(self, response: str) -> str:
        """
        获取清理后的回复（移除跳转指令）
        
        Args:
            response: 原始回复
            
        Returns:
            清理后的回复
        """
        # 先清洗括号内“动作/神态/旁白式描写”
        cleaned = self._strip_paren_action_and_stage_directions(response)
        # 再移除跳转指令
        cleaned = self._transition_pattern.sub("", cleaned)
        return cleaned.strip()
    
    def reset(self):
        """重置对话历史"""
        self.history = []
    
    def get_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self.history
        ]
    
    def _call_llm(self, messages: List[dict]) -> str:
        """调用 LLM API，返回回复文本。"""
        try:
            return call_chat_completion(
                self.api_url,
                self.api_key,
                self.model,
                messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                service_code=self.service_code,
                timeout=60,
            )
        except Exception as e:
            raise RuntimeError(f"API 调用失败: {e}")
    
    def update_system_prompt(self, new_prompt: str):
        """
        更新系统提示词（用于场景切换）
        
        Args:
            new_prompt: 新的系统提示词
        """
        self.system_prompt = new_prompt
    
    def switch_to_card(self, card_prompt: str, preserve_history: bool = True):
        """
        切换到新的卡片
        
        Args:
            card_prompt: 新卡片的prompt
            preserve_history: 是否保留历史对话
        """
        self.system_prompt = card_prompt
        if not preserve_history:
            self.history = []


class NPCFactory:
    """NPC工厂，用于创建不同配置的NPC"""
    
    @staticmethod
    def create_from_env(card_prompt: str) -> LLMNPC:
        """
        从环境变量创建NPC
        
        Args:
            card_prompt: A类卡片的prompt
            
        Returns:
            配置好的LLMNPC实例
        """
        import os
        import importlib

        try:
            load_dotenv = importlib.import_module("dotenv").load_dotenv
        except Exception:  # pragma: no cover - 测试/静态分析环境下可缺失 dotenv
            load_dotenv = lambda: None
        
        load_dotenv()
        defaults = get_simulator_default_config()
        config = {
            "api_url": os.getenv("NPC_API_URL", os.getenv("SIMULATOR_API_URL", defaults["api_url"])),
            "api_key": os.getenv("NPC_API_KEY", os.getenv("SIMULATOR_API_KEY", defaults["api_key"])),
            "model": os.getenv("NPC_MODEL", os.getenv("CARD_MODEL_ID", defaults["model"])),
            "service_code": os.getenv("NPC_SERVICE_CODE", os.getenv("SIMULATOR_SERVICE_CODE", LLMNPC.DEFAULT_SERVICE_CODE)),
        }
        return LLMNPC(card_prompt, config)
    
    @staticmethod
    def create_with_card_config(card_prompt: str, card_model_id: str = "") -> LLMNPC:
        """
        使用卡片中的模型配置创建NPC
        
        Args:
            card_prompt: A类卡片的prompt
            card_model_id: 卡片中配置的模型ID
            
        Returns:
            配置好的LLMNPC实例
        """
        import os
        import importlib

        try:
            load_dotenv = importlib.import_module("dotenv").load_dotenv
        except Exception:  # pragma: no cover - 测试/静态分析环境下可缺失 dotenv
            load_dotenv = lambda: None
        
        load_dotenv()
        defaults = get_simulator_default_config()
        model = card_model_id if card_model_id else os.getenv("CARD_MODEL_ID", defaults["model"])
        config = {
            "api_url": os.getenv("NPC_API_URL", os.getenv("SIMULATOR_API_URL", defaults["api_url"])),
            "api_key": os.getenv("NPC_API_KEY", os.getenv("SIMULATOR_API_KEY", defaults["api_key"])),
            "model": model,
            "service_code": os.getenv("NPC_SERVICE_CODE", os.getenv("SIMULATOR_SERVICE_CODE", LLMNPC.DEFAULT_SERVICE_CODE)),
        }
        return LLMNPC(card_prompt, config)
