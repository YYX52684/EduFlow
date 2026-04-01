"""
DSPy 卡片生成器的统一工具函数
提取公共逻辑，避免重复代码
"""

import re
import hashlib
import threading
import functools
from collections import deque
from typing import List, Optional, Callable, Any, Sequence


_POSITIVE_FEEDBACK_KEYWORDS = [
    "很好", "很棒", "不错", "太棒了", "做得好", "做得不错", "回答得不错",
    "思路清晰", "表达清楚", "表述准确", "理解到位", "抓住重点", "抓到关键",
    "方向对了", "分析到位", "判断准确", "回答完整", "有理有据", "说得很清楚",
    "肯定", "认可", "鼓励", "表扬", "赞赏", "亮点"
]

_GENERIC_POSITIVE_FEEDBACK_PHRASES = [
    "方向对了。",
    "这个点抓住了。",
    "思路基本正确。",
    "这个判断可用。",
    "主线没偏。",
    "这个回答到位。",
]

_EVIDENCE_POSITIVE_FEEDBACK_PHRASES = [
    "能把依据讲出来，说明你不是在凭感觉回答。",
    "你已经开始用证据支撑判断了，这一点很好。",
    "这个回答有依据，可信度就上来了。",
    "能说到判断依据，说明你抓住了关键。",
    "你把支撑理由带出来了，方向是对的。",
    "这不是泛泛而谈，能落到依据上就很有价值。",
    "能把判断和依据连起来，这一步很关键。",
    "你已经不只是在给结论了，证据意识不错。",
    "这个回答有理有据，继续保持这种表达方式。",
    "把依据说清楚之后，答案就更站得住了。",
]

_PROCESS_POSITIVE_FEEDBACK_PHRASES = [
    "步骤脉络已经理顺了，接着把关键环节补完整。",
    "你对先后顺序抓得不错，再把每一步的目的说清楚。",
    "这个流程意识是对的，继续把关键节点补出来。",
    "顺序没有乱，下面再把重点步骤压实。",
    "你已经把操作路径理出来了，再把风险点带上。",
    "这条流程线基本清楚了，继续把关键动作说具体。",
    "步骤抓得住，接着把最容易出错的地方补上。",
    "你已经把主流程说出来了，下面补关键判断点。",
    "这个操作思路是顺的，再把关键细节压实一点。",
    "流程框架已经出来了，继续把决定成败的环节说清楚。",
]

_REASONING_POSITIVE_FEEDBACK_PHRASES = [
    "这个判断不是泛泛而谈，说明你在动脑分析。",
    "你已经抓到问题的逻辑了，接着把原因展开。",
    "这个理解比较到位，再把关键原理补一层。",
    "概念没有说偏，继续把背后的逻辑讲清楚。",
    "你已经摸到核心原理了，再把它和情境扣紧。",
    "这个分析方向对，再把判断链条补完整。",
    "你抓住了关键关系，继续把推理讲顺。",
    "表述已经比较准确了，下面再把最关键的原因说透。",
    "逻辑主线是清楚的，继续把决定性的那一点补足。",
    "你的分析已经接近核心了，再把关键差异说出来。",
]

_POSITIVE_FEEDBACK_HISTORY = deque(maxlen=10)
_POSITIVE_FEEDBACK_LOCK = threading.Lock()


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


def reset_positive_feedback_history() -> None:
    """在每次生成新文档前重置短语历史，避免跨文档串味。"""
    with _POSITIVE_FEEDBACK_LOCK:
        _POSITIVE_FEEDBACK_HISTORY.clear()


def has_explicit_positive_feedback(text: str) -> bool:
    """文本中是否已经包含明显的正向反馈。"""
    if not text:
        return False
    return any(keyword in text for keyword in _POSITIVE_FEEDBACK_KEYWORDS)


def _dedupe_preserve_order(items: Sequence[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _build_positive_feedback_pool(text: str) -> List[str]:
    pool: List[str] = list(_GENERIC_POSITIVE_FEEDBACK_PHRASES)
    if re.search(r"数据|依据|证据|参数|标准|指标|计算|结果", text):
        pool.extend(_EVIDENCE_POSITIVE_FEEDBACK_PHRASES)
    if re.search(r"步骤|流程|顺序|工序|环节|操作|过程", text):
        pool.extend(_PROCESS_POSITIVE_FEEDBACK_PHRASES)
    if re.search(r"原理|逻辑|概念|判断|分析|推理|关系", text):
        pool.extend(_REASONING_POSITIVE_FEEDBACK_PHRASES)
    if len(pool) == len(_GENERIC_POSITIVE_FEEDBACK_PHRASES):
        pool.extend(_REASONING_POSITIVE_FEEDBACK_PHRASES[:5])
    return _dedupe_preserve_order(pool)


def select_diverse_phrase(
    seed_text: str,
    phrases: Sequence[str],
    recent_phrases: Optional[Sequence[str]] = None,
) -> str:
    """
    基于 seed_text 稳定排序短语，并尽量避开最近刚用过的表达。
    """
    candidates = _dedupe_preserve_order(phrases)
    if not candidates:
        raise ValueError("phrases 不能为空")

    ranked = sorted(
        candidates,
        key=lambda phrase: hashlib.sha256(
            f"{seed_text}\n{phrase}".encode("utf-8")
        ).hexdigest(),
    )
    recent = set(recent_phrases or [])
    for phrase in ranked:
        if phrase not in recent:
            return phrase
    return ranked[0]


def should_inject_positive_feedback(text: str) -> bool:
    """
    仅在文本明显缺少正向反馈时，稀疏地补一条激励语，避免每张卡都同一腔调。
    """
    if not text:
        return False

    stripped = text.strip()
    if not stripped or has_explicit_positive_feedback(stripped):
        return False

    # 文本本身已经较丰满时，不再强行补一句。
    if len(stripped) >= 180:
        return False
    if len(re.findall(r"[。！？!?；;]", stripped)) >= 4:
        return False

    # 稀疏注入：让“补一句表扬”退回兜底策略，而不是每张卡的固定尾巴。
    bucket = int(hashlib.sha256(stripped.encode("utf-8")).hexdigest()[:8], 16) % 100
    return bucket < 15


def _append_sentence(text: str, sentence: str) -> str:
    stripped = text.rstrip()
    if not stripped:
        return sentence
    if stripped.endswith(("。", "！", "？", "；", "!", "?", ";")):
        return f"{stripped}{sentence}"
    return f"{stripped}。{sentence}"


def inject_optional_positive_feedback(text: str) -> str:
    """在极少数缺少鼓励语的交互说明里补一条更自然、可去重的正向反馈。"""
    if not should_inject_positive_feedback(text):
        return text

    with _POSITIVE_FEEDBACK_LOCK:
        chosen = select_diverse_phrase(
            text,
            _build_positive_feedback_pool(text),
            list(_POSITIVE_FEEDBACK_HISTORY),
        )
        _POSITIVE_FEEDBACK_HISTORY.append(chosen)
    return _append_sentence(text, chosen)


def normalize_interaction_text(text: str) -> str:
    """将 Interaction 规范为结构化文本，保留必要换行与要点格式。"""
    if not text:
        return text

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""

    paragraphs = []
    for chunk in re.split(r"\n\s*\n+", normalized):
        item = chunk.strip()
        if not item:
            continue
        item = re.sub(r"^#\s*Interaction[:：]?\s*", "", item, flags=re.IGNORECASE)
        # 仅清理每行首尾空白，保留多轮策略所需的标题/要点结构
        item = "\n".join(line.strip() for line in item.split("\n") if line.strip())
        if item:
            paragraphs.append(item)

    return "\n\n".join(paragraphs)


def _sanitize_dialogue_line(line: str) -> str:
    """对单行互动文本做反 AI 味净化，不处理 markdown 结构行。"""
    s = line.strip()
    if not s:
        return s
    if s.startswith(("#", "-", "*")):
        return s

    # 去掉教学提示腔
    s = re.sub(r"(^|[。！？!?；;])\s*提示[:：]\s*", r"\1", s)
    # 去掉“你提到的...”开头复述腔
    s = re.sub(r"(^|[。！？!?；;])\s*你提到的(?:这些)?", r"\1", s)

    # 压缩冗长表扬前缀，改为短反馈
    praise_words = ("不错", "很好", "很专业", "很全面", "很到位", "挺好")
    m = re.match(r"^\s*([^。！？!?]{18,140})([。！？!?])", s)
    if m and any(word in m.group(1) for word in praise_words):
        rest = s[m.end():].lstrip()
        if rest:
            s = f"这个方向对了。{rest}"

    # 清理多余空白与标点
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[，、]\s*[，、]+", "，", s)
    s = re.sub(r"[。！？!?；;]\s*[。！？!?；;]+", "。", s)
    return s


def sanitize_interaction_style(text: str) -> str:
    """净化 Interaction 文风：去提示腔、去复述腔、压缩冗长表扬。"""
    if not text:
        return text
    lines = text.split("\n")
    cleaned = [_sanitize_dialogue_line(line) for line in lines]
    return "\n".join(cleaned).strip()


def post_process_fields(
    obj: Any,
    fields: List[str],
    inject_positive_feedback: bool = True,
) -> None:
    """
    对对象的指定字段进行后处理：移除括号内容
    
    Args:
        obj: 包含字段的对象（如 dspy.Prediction）
        fields: 需要处理的字段名列表
        inject_positive_feedback: 是否对 interaction_section 兜底补充正向反馈
    """
    for field in fields:
        text = getattr(obj, field, '')
        if text and contains_brackets(text):
            setattr(obj, field, strip_brackets(text))
        if field == 'interaction_section':
            current = getattr(obj, field, '')
            if isinstance(current, str) and current:
                current = normalize_interaction_text(current)
                current = sanitize_interaction_style(current)
                setattr(obj, field, current)
        # 针对交互体验性强的字段，注入正向激励（使用当前值，确保括号已清理）
        if inject_positive_feedback and field == 'interaction_section':
            current = getattr(obj, field, '')
            if isinstance(current, str) and current:
                setattr(obj, field, inject_optional_positive_feedback(current))


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
