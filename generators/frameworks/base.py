"""
框架库基类
所有生成框架需继承 BaseCardGenerator 并实现 generate_all_cards
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Any


class BaseCardGenerator(ABC):
    """卡片生成器抽象基类"""

    @abstractmethod
    def generate_all_cards(
        self,
        stages: List[dict],
        original_content: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        **kwargs: Any
    ) -> str:
        """
        生成所有阶段的 A/B 类卡片

        Args:
            stages: 阶段信息列表
            original_content: 完整的原始剧本内容
            progress_callback: 进度回调，接收 (current, total, message)
            **kwargs: 各框架可选的额外参数（如 b_card_mode）

        Returns:
            合并后的所有卡片内容（A1-B1-A2-B2... 格式）
        """
        pass
