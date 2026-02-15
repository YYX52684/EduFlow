"""
LLM学生模拟器
使用 LLM 扮演学生角色。默认使用 DeepSeek，与卡片生成一致；可通过 SIMULATOR_* 环境变量覆盖。
"""

import os
import requests
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from .student_persona import StudentPersona


@dataclass
class StudentMessage:
    """学生消息"""
    content: str
    metadata: dict = field(default_factory=dict)


def _default_student_config():
    from config import DEEPSEEK_CHAT_URL, DEEPSEEK_API_KEY, DEEPSEEK_MODEL
    return {
        "api_url": DEEPSEEK_CHAT_URL,
        "api_key": DEEPSEEK_API_KEY or "",
        "model": DEEPSEEK_MODEL,
    }


class LLMStudent:
    """LLM学生模拟器"""
    
    # 默认配置（DeepSeek）；可通过环境变量 SIMULATOR_* 覆盖
    DEFAULT_SERVICE_CODE = ""
    
    def __init__(self, persona: StudentPersona, config: dict = None):
        """
        初始化学生模拟器
        
        Args:
            persona: 学生人设
            config: 配置字典，包含：
                - api_url: API地址
                - api_key: API密钥
                - model: 模型名称
                - service_code: 服务代码
                - max_tokens: 最大token数
                - temperature: 温度参数
        """
        config = config or {}
        defaults = _default_student_config()
        self.persona = persona
        self.system_prompt = persona.to_system_prompt()
        self.api_url = config.get("api_url", defaults["api_url"])
        self.api_key = config.get("api_key", defaults["api_key"])
        self.model = config.get("model", defaults["model"])
        self.service_code = config.get("service_code", self.DEFAULT_SERVICE_CODE)
        self.max_tokens = config.get("max_tokens", 200)  # 学生单轮约 50–100 字
        self.temperature = config.get("temperature", 0.8)
        
        # 对话历史
        self.history: List[Dict[str, str]] = []
        
        # 场景上下文（用于学生理解当前情境）
        self.scene_context: str = ""
    
    def set_scene_context(self, context: str):
        """
        设置场景上下文
        
        Args:
            context: 场景描述，帮助学生理解当前情境
        """
        self.scene_context = context
    
    def generate_response(self, npc_message: str, context: Optional[List[dict]] = None) -> str:
        """
        根据NPC消息生成学生回复
        
        Args:
            npc_message: NPC的消息
            context: 额外上下文（可选）
            
        Returns:
            学生的回复
        """
        # 构建消息列表
        messages = self._build_messages(npc_message)
        
        # 调用API
        response = self._call_llm(messages)
        
        # 记录历史
        self.history.append({"role": "npc", "content": npc_message})
        self.history.append({"role": "student", "content": response})
        
        return response
    
    def _build_messages(self, npc_message: str) -> List[dict]:
        """构建消息列表"""
        # 构建系统提示
        system_content = self.system_prompt
        
        # 添加场景上下文
        if self.scene_context:
            system_content += f"\n\n## 当前场景\n{self.scene_context}"
        
        messages = [
            {"role": "system", "content": system_content}
        ]
        
        # 添加历史对话
        for msg in self.history:
            role = "user" if msg["role"] == "npc" else "assistant"
            messages.append({"role": role, "content": msg["content"]})
        
        # 添加当前NPC消息
        messages.append({"role": "user", "content": npc_message})
        
        return messages
    
    def _call_llm(self, messages: List[dict]) -> str:
        """
        调用LLM API
        
        Args:
            messages: 消息列表
            
        Returns:
            LLM的回复
        """
        headers = {
            "Content-Type": "application/json",
        }
        
        # 添加认证信息
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.service_code:
            headers["serviceCode"] = self.service_code
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 解析OpenAI格式的响应
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            
            # 尝试其他格式
            if "content" in result:
                return result["content"]
            if "response" in result:
                return result["response"]
            
            raise ValueError(f"无法解析API响应: {result}")
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API调用失败: {e}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"响应解析失败: {e}")
    
    def reset(self):
        """重置对话历史"""
        self.history = []
        self.scene_context = ""
    
    def get_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return self.history.copy()
    
    def update_persona(self, persona: StudentPersona):
        """
        更新学生人设
        
        Args:
            persona: 新的人设
        """
        self.persona = persona
        self.system_prompt = persona.to_system_prompt()


class StudentFactory:
    """学生模拟器工厂"""
    
    @staticmethod
    def create_from_env(persona: StudentPersona) -> LLMStudent:
        """
        从环境变量创建学生模拟器
        
        Args:
            persona: 学生人设
            
        Returns:
            配置好的LLMStudent实例
        """
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        defaults = _default_student_config()
        config = {
            "api_url": os.getenv("SIMULATOR_API_URL", defaults["api_url"]),
            "api_key": os.getenv("SIMULATOR_API_KEY", defaults["api_key"]),
            "model": os.getenv("SIMULATOR_MODEL", defaults["model"]),
            "service_code": os.getenv("SIMULATOR_SERVICE_CODE", LLMStudent.DEFAULT_SERVICE_CODE),
        }
        return LLMStudent(persona, config)
    
    @staticmethod
    def create_with_preset(preset_name: str, config: dict = None) -> LLMStudent:
        """
        使用预设人设创建学生模拟器
        
        Args:
            preset_name: 预设名称 (excellent/average/struggling)
            config: 配置字典（可选）
            
        Returns:
            配置好的LLMStudent实例
        """
        from .student_persona import PersonaManager
        
        manager = PersonaManager()
        persona = manager.get_persona(preset_name)
        
        if config:
            return LLMStudent(persona, config)
        return StudentFactory.create_from_env(persona)


class ManualStudent:
    """手动输入模式的学生（用于测试）"""
    
    def __init__(self, name: str = "手动输入"):
        self.name = name
        self.history: List[Dict[str, str]] = []
    
    def generate_response(self, npc_message: str, context: Optional[List[dict]] = None) -> str:
        """
        手动输入学生回复
        
        Args:
            npc_message: NPC的消息
            context: 额外上下文（可选）
            
        Returns:
            用户输入的回复
        """
        print(f"\n[NPC]: {npc_message}")
        print("-" * 40)
        
        # 等待用户输入
        response = input("[学生] 请输入回复 (输入 'q' 退出): ").strip()
        
        if response.lower() == 'q':
            raise KeyboardInterrupt("用户选择退出")
        
        # 记录历史
        self.history.append({"role": "npc", "content": npc_message})
        self.history.append({"role": "student", "content": response})
        
        return response
    
    def reset(self):
        """重置对话历史"""
        self.history = []
    
    def get_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return self.history.copy()
