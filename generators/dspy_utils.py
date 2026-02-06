"""
DSPy 卡片生成器的统一工具函数
提取公共逻辑，避免重复代码
"""

import re
import functools
from typing import List, Optional, Callable, Any


def contains_brackets(text: str) -> bool:
    """检查文本是否包含括号（中文或英文）"""
    if not text:
        return False
    bracket_patterns = [
        r'（.*?）',  # 中文括号
        r'\(.*?\)',  # 英文括号
        r'【.*?】',  # 中文方括号
        r'\[.*?\]',  # 英文方括号
    ]
    for pattern in bracket_patterns:
        if re.search(pattern, text):
            return True
    return False


def strip_brackets(text: str) -> str:
    """移除文本中的括号及其内容，用于后处理 LLM 输出"""
    if not text:
        return text
    # 按顺序移除各类括号及其内容
    for pattern in [r'（.*?）', r'\(.*?\)', r'【.*?】', r'\[.*?\]']:
        text = re.sub(pattern, '', text)
    # 清理可能产生的多余空格或标点
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'[，。、；]\s*[，。、；]', '，', text)
    return text


def post_process_fields(obj: Any, fields: List[str]) -> None:
    """
    对对象的指定字段进行后处理：移除括号内容
    
    Args:
        obj: 包含字段的对象（如 dspy.Prediction）
        fields: 需要处理的字段名列表
    """
    def inject_positive_feedback(text: str) -> str:
        if not text:
            return text
        # 针对 interaction_section，若文本中未出现明确正向反馈，给出多样化的正向激励
        positive_keywords = ["很好", "很棒", "思路清晰", "数据支撑很好", "表述准确", "清晰"]
        if any(p in text for p in positive_keywords):
            return text
        phrases = [
            "很棒，这个思路很清晰。",
            "不错，思路清晰，数据支撑也到位。",
            "很好，这个回答很具体，继续保持。"
        ]
        # 使用文本长度来挑选一个固定的短语，避免完全随机带来不可重复性
        chosen = phrases[len(text) % len(phrases)]
        return text.rstrip() + " " + chosen

    for field in fields:
        text = getattr(obj, field, '')
        if text and contains_brackets(text):
            setattr(obj, field, strip_brackets(text))
        # 针对交互体验性强的字段，注入正向激励（使用当前值，确保括号已清理）
        if field == 'interaction_section':
            current = getattr(obj, field, '')
            if isinstance(current, str) and current:
                setattr(obj, field, inject_positive_feedback(current))


def with_bracket_cleanup(fields: List[str]):
    """
    装饰器：自动对函数返回的对象进行括号清理
    
    Usage:
        @with_bracket_cleanup(['role_section', 'context_section'])
        def forward(self, ...):
            result = self.generate(...)
            return result
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            result = func(*args, **kwargs)
            post_process_fields(result, fields)
            return result
        return wrapper
    return decorator


def is_same_role(current_role: str, next_role: str) -> bool:
    """
    判断前后角色是否相同（模糊匹配）
    
    Args:
        current_role: 当前角色描述
        next_role: 下一个角色描述
        
    Returns:
        是否相同角色
    """
    if not current_role or not next_role:
        return True  # 如果角色信息缺失，默认视为同一角色
    
    # 提取角色名称的核心部分进行比较
    # 例如 "陈新农，资深现代农业投资人" 和 "陈新农，一位经验丰富的投资人" 应该视为同一角色
    current_name = current_role.split('，')[0].split(',')[0].strip()
    next_name = next_role.split('，')[0].split(',')[0].strip()
    
    return current_name == next_name


def estimate_length(text: str) -> int:
    """
    估算文本长度（中文字符 + 英文单词）
    
    Args:
        text: 输入文本
        
    Returns:
        估算长度
    """
    if not text:
        return 0
    
    # 中文字符算1个字
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    # 英文单词算1个字（简单估算）
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    
    return chinese_chars + english_words


def generate_length_guidance(target_min: int, target_max: int, field_desc: str = "") -> str:
    """
    生成长度指导文本，用于提示词
    
    Args:
        target_min: 目标最小长度
        target_max: 目标最大长度
        field_desc: 字段描述
        
    Returns:
        长度指导文本
    """
    return f"长度建议{target_min}-{target_max}字，保持简洁自然即可，不必严格限制。"


class Retryable:
    """带重试机制的函数包装器"""
    
    def __init__(
        self, 
        max_retries: int = 3,
        exceptions: tuple = (Exception,),
        on_retry: Optional[Callable[[int, Exception], None]] = None
    ):
        self.max_retries = max_retries
        self.exceptions = exceptions
        self.on_retry = on_retry
    
    def __call__(self, func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except self.exceptions as e:
                    last_exception = e
                    if attempt < self.max_retries:
                        if self.on_retry:
                            self.on_retry(attempt, e)
                    else:
                        raise last_exception
            return None
        return wrapper


def format_card_section(title: str, content: str) -> str:
    """格式化卡片章节"""
    return f"# {title}\n{content}\n"


def ensure_constraint(constraints: str, keyword: str, default_constraint: str) -> str:
    """
    确保约束条件中包含特定关键词，如果不存在则添加默认约束
    
    Args:
        constraints: 原始约束文本
        keyword: 需要检查的关键词
        default_constraint: 默认要添加的约束
        
    Returns:
        确保后的约束文本
    """
    if keyword not in constraints:
        return f"- {default_constraint}\n{constraints}"
    return constraints
