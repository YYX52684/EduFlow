"""
学生模拟测试模块

支持两种测试模式：
1. 本地模拟：从 output/cards_output_*.md 文件加载卡片prompt
2. 平台拉取：调用教师端API获取已配置项目的卡片数据

核心组件：
- CardLoader: 卡片加载器（本地/平台）
- LLMNPC: LLM NPC模拟器（使用卡片中的prompt）
- StudentPersona: 学生人设管理
- LLMStudent: LLM学生模拟器
- SessionRunner: 交互会话运行器
- Evaluator: 交互质量评估器
"""

from .card_loader import LocalCardLoader, PlatformCardLoader, CardData
from .llm_npc import LLMNPC
from .student_persona import StudentPersona, PersonaManager, PersonaGenerator, PersonaGeneratorFactory
from .llm_student import LLMStudent
from .session_runner import SessionRunner, SessionConfig
from .evaluator import Evaluator, evaluate_session

__all__ = [
    "LocalCardLoader",
    "PlatformCardLoader", 
    "CardData",
    "LLMNPC",
    "StudentPersona",
    "PersonaManager",
    "PersonaGenerator",
    "PersonaGeneratorFactory",
    "LLMStudent",
    "SessionRunner",
    "SessionConfig",
    "Evaluator",
    "evaluate_session",
]
