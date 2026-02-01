"""
传统生成框架：基于 OpenAI API 的卡片生成
"""
from typing import List, Optional, Callable, Any

from ..base import BaseCardGenerator

try:
    from ...card_generator import CardGenerator
    _AVAILABLE = True
except ImportError:
    CardGenerator = None
    _AVAILABLE = False


FRAMEWORK_ID = "default"
FRAMEWORK_NAME = "传统生成"
FRAMEWORK_DESCRIPTION = "基于 OpenAI API 的卡片生成，兼容 DeepSeek 等接口"


class DefaultFramework(BaseCardGenerator):
    """传统生成器框架封装"""

    def __init__(self, api_key: Optional[str] = None):
        if not _AVAILABLE:
            raise ImportError("请先安装 openai 库: pip install openai")
        self._gen = CardGenerator(api_key=api_key)

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
GeneratorClass = DefaultFramework if _AVAILABLE else None
