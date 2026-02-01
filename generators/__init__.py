"""
生成器模块
包含内容分割器和卡片生成器

卡片生成框架库（generators/frameworks/）：
- 可用 list_frameworks() 列出所有框架，get_framework(id) 获取框架类
- 开发者可在 frameworks/ 下新增子目录实现新框架，自动被发现
"""
from .content_splitter import ContentSplitter
from .card_generator import CardGenerator

# DSPy生成器可能需要额外安装dspy-ai
try:
    from .dspy_card_generator import DSPyCardGenerator
    DSPY_AVAILABLE = True
except ImportError:
    DSPyCardGenerator = None
    DSPY_AVAILABLE = False

# 框架库：发现与选择
from .frameworks import list_frameworks, get_framework

__all__ = [
    "ContentSplitter",
    "CardGenerator",
    "DSPyCardGenerator",
    "DSPY_AVAILABLE",
    "list_frameworks",
    "get_framework",
]
