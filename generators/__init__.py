"""
生成器模块
包含内容分割器和卡片生成器

卡片生成框架库（generators/frameworks/）：
- 可用 list_frameworks() 列出所有框架，get_framework(id) 获取框架类
- 开发者可在 frameworks/ 下新增子目录实现新框架，自动被发现
"""
from .content_splitter import ContentSplitter

# DSPy 生成器可能需要额外安装 dspy-ai
try:
    from .dspy_card_orchestrator import DSPyCardGenerator
    DSPY_AVAILABLE = True
except ImportError:
    DSPyCardGenerator = None
    DSPY_AVAILABLE = False

try:
    from .dspy_training_doc_orchestrator import TrainingDocGenerator
    TRAINING_DOC_GENERATOR_AVAILABLE = True
except ImportError:
    TrainingDocGenerator = None
    TRAINING_DOC_GENERATOR_AVAILABLE = False

# 框架库：发现与选择
from .frameworks import list_frameworks, get_framework

__all__ = [
    "ContentSplitter",
    "DSPyCardGenerator",
    "DSPY_AVAILABLE",
    "TrainingDocGenerator",
    "TRAINING_DOC_GENERATOR_AVAILABLE",
    "list_frameworks",
    "get_framework",
]
