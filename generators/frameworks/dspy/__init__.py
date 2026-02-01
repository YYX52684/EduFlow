"""
DSPy 生成框架：基于 DSPy 的结构化卡片生成
"""
from typing import List, Optional, Callable, Any

from ..base import BaseCardGenerator

try:
    from ...dspy_card_generator import DSPyCardGenerator
    _AVAILABLE = True
except ImportError:
    DSPyCardGenerator = None
    _AVAILABLE = False


FRAMEWORK_ID = "dspy"
FRAMEWORK_NAME = "DSPy 结构化生成"
FRAMEWORK_DESCRIPTION = "基于 DSPy 的结构化生成，可减少括号等违规输出"


class DSPyFramework(BaseCardGenerator):
    """DSPy 生成器框架封装"""

    def __init__(self, api_key: Optional[str] = None):
        if not _AVAILABLE:
            raise ImportError("请先安装 dspy-ai: pip install dspy-ai")
        self._gen = DSPyCardGenerator(api_key=api_key)

    def generate_all_cards(
        self,
        stages: List[dict],
        original_content: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        **kwargs: Any
    ) -> str:
        return self._gen.generate_all_cards(
            stages, original_content, progress_callback=progress_callback
        )


# 供发现逻辑使用：仅当依赖可用时暴露
GeneratorClass = DSPyFramework if _AVAILABLE else None
