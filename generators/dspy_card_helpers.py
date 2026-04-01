"""
DSPy 卡片生成的纯函数辅助逻辑。

将规则判断、展示层约束整理、阶段元数据和 Markdown 格式化从主生成器中拆出，
让 `DSPyCardGenerator` 只负责 LLM 调用与生成编排。
"""

import json
import re
from typing import Any, Dict, List, Optional

from .dspy_utils import format_card_section

_GUIDANCE_KEYWORDS = ("讲解", "指导型", "讲授", "展示步骤", "指导讲解")
_QA_OVERRIDE_KEYWORDS = ("提问", "追问", "考核", "评价", "诊断", "鉴别")
_GUIDANCE_DISCIPLINE_KEYWORDS = (
    "社工", "社会工作", "心理", "咨询", "沟通", "访谈", "共情", "患者沟通", "家访", "辅导"
)
_QA_DISCIPLINE_KEYWORDS = (
    "机械", "工程", "实验", "检验", "诊断", "鉴别", "工艺", "参数", "设备", "施工", "电子"
)
_GUIDANCE_TASK_HINTS = ("同理", "共情", "倾听", "情绪支持", "感受", "复述确认")
_QA_TASK_HINTS = ("判断依据", "原因分析", "风险点", "参数", "步骤", "方案", "追问", "考核")
_FOLLOW_UP_KEYWORDS = (
    "原因", "依据", "为什么", "判断", "分析", "诊断", "鉴别", "评估",
    "解释", "复述", "确认", "澄清", "核实", "风险", "推理",
)
_GENERATION_ONLY_CONSTRAINT_PATTERNS = (
    re.compile(r"信息密度|锚点|key_points|content_excerpt", re.IGNORECASE),
    re.compile(r"原文要点|原文具体信息|不得只作概括性说明"),
    re.compile(r"涉及英文/代码/长串|编号选项|朗读原文"),
    re.compile(r"至少追问1次|至少追问一次"),
    re.compile(r"覆盖.*要点"),
)
_MAX_A_CARD_CONSTRAINTS = 4
_B_CARD_SIMPLE_DISPLAY_CONSTRAINTS = (
    "优先基于 `${previous_dialogue}` 最近1-2轮回应，先点名具体术语/参数/错误点，再推进下一步动作。",
    "禁止静态评语模板与上帝视角总结，少做整段总评，不用「本环节」「下一阶段」等流程话术。",
    "Response Logic 必须可执行：按「锚定-回应-推进」生成话术，不要预写固定台词。",
)
_B_CARD_NARRATOR_DISPLAY_CONSTRAINTS = (
    "优先基于 `${previous_dialogue}` 最近1-2轮回应，先点名具体术语/参数/错误点，再推进下一步动作。",
    "禁止静态评语模板与上帝视角总结，不用「本环节」「下一阶段」等流程话术。",
    "旁白只作简短衔接，采用「锚定-回应-推进」骨架，不要长篇第三人称叙述。",
)
_ENDING_DISPLAY_CONSTRAINTS = (
    "只做这一轮自然收尾，不再开启新话题。",
    "保持角色口吻结束，不提卡片编号或下一阶段。",
    "语言简洁自然，可直接朗读。",
)
_A_RUNTIME_LENGTH_CONSTRAINT = "运行时单次回复建议150-200词，最长不超过250词。"
_A_ANTI_LOOP_CONSTRAINT = "同一小知识点最多连续追问2轮；若两轮内没有新增信息，先做阶段性收束并切换到本幕下一个要点。"
_B_RUNTIME_LENGTH_CONSTRAINT = "运行时单次回复建议50-120词，最长不超过150词。"

_DISALLOWED_EMOTION_WORDS = (
    # 负向情绪（按常见表达覆盖）
    "失落",
    "孤独",
    "悲伤",
    "难过",
    "沮丧",
    "焦虑",
    "紧张",
    "害怕",
    "恐惧",
    "愤怒",
    "生气",
    "无奈",
    "绝望",
    "失望",
    "忧郁",
    "抑郁",
    "压抑",
    "沮丧",
    # 正向情绪（若出现也可能被模型“台词化”，此处按需求一律移除）
    "开心",
    "快乐",
    "喜悦",
    "兴奋",
    "激动",
    "感动",
)

_DISALLOWED_ROLE_DELIVERY_PHRASES = (
    # 明确提到的“动作/口吻描写”类型
    "语速平缓",
    # 语速/语调/口吻类
    "语速",
    "语气",
    "语调",
    "口语化",
    # 常见神态/动作（角色卡常会被模型台词化成“你微笑着说道”）
    "微笑着",
    "笑着",
    "点头",
    "摇头",
    "看向",
    "注视",
    "凝视",
    "轻声",
    "低声",
)

_B_STATIC_TEMPLATE_PATTERNS = (
    re.compile(r"你在回答中对[^。]{0,60}有一定[^。]{0,80}[。；]?"),
    re.compile(r"不过[^。]{0,80}(还可以更深入|还有待完善)[^。]{0,60}[。；]?"),
    re.compile(r"就像我们讨论的[，,]?"),
    re.compile(r"接下来，我们可以思考"),
    re.compile(r"在确定[^。]{0,60}上还有待完善[。；]?"),
    re.compile(r"(总结汇报|思政体现|进入下一阶段|转入下一阶段)"),
)


def _sanitize_b_response_logic_text(response_logic: str, stage: Optional[dict] = None) -> str:
    """去静态模板，并将 B 卡输出规整为可执行的 Response Logic。"""
    text = (response_logic or "").strip()
    if not text:
        return text

    for pattern in _B_STATIC_TEMPLATE_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"\s+", " ", text).strip("，,。；; ")

    stage = stage or {}
    key_points = stage.get("key_points") or []
    anchor = next((str(k).strip() for k in key_points if str(k).strip()), "")
    has_anchor = bool(anchor and anchor in text)
    if anchor and not has_anchor:
        text = f"锚定：优先点名学生上一轮提到的“{anchor}”或同类关键术语。 {text}".strip()

    has_next_action = bool(re.search(r"(请|先|继续|补充|说明|列出|给出|接着|再说|下一步|参数|指标)", text))
    if not has_next_action:
        text = f"{text} 推进：抛出一个落地问题，要求学生说明改造后先变化的运行参数及对应监控指标。".strip()

    text = re.sub(r"\s+", " ", text).strip()

    # 若模型仍产出“台词句”，重写为可执行规则骨架。
    has_logic_markers = all(marker in text for marker in ("锚定", "回应", "推进"))
    if not has_logic_markers:
        response_line = "回应：根据学生最后一轮的正确点或偏差，给一句确认或纠偏，不做泛泛总评。"
        branch_line = "分支：答到关键点时短肯定并推进；答偏时先指出遗漏再推进。"
        advance_line = "推进：立刻提出落地问题，优先询问改造后先变化的运行参数与监控指标。"
        anchor_line = "锚定：先引用 `${previous_dialogue}` 最近1-2轮中的具体术语、参数、结论或错误点。"
        return "\n".join([anchor_line, response_line, branch_line, advance_line])

    return text


def sanitize_npc_role_text(npc_role_text: str) -> str:
    """
    清洗喂给 LLM 的 NPC 角色设定字段，避免出现：
    1) “情绪词汇”（如“失落/孤独”）；
    2) “语速/神态/动作/口吻描写”（如“语速平缓”）。

    只针对输入的“设定文本”，不影响最终卡片输出的“Interaction 动作描写”清洗策略。
    """
    if not npc_role_text or not str(npc_role_text).strip():
        return npc_role_text

    s = str(npc_role_text).strip()

    # 先移除“你感到/感到 + 情绪词”这种情绪子句，尽量保留句子其余事实。
    # 例："...，你感到失落和孤独。" -> "...，"
    emotion_alt = "|".join(re.escape(w) for w in _DISALLOWED_EMOTION_WORDS)
    s = re.sub(
        rf"(?:[，、])?\s*(?:你\s*)?感到\s*(?:{emotion_alt})(?:\s*(?:和|与|及)\s*(?:{emotion_alt}))*\s*[，。！？!?]?",
        "",
        s,
    )
    # 兜底：直接删掉零散情绪词，确保不出现在最终提示词中。
    s = re.sub(rf"(?:{emotion_alt})", "", s)
    # 删掉删除情绪词后可能残留的连接词（和/与/及）+ 句末符号。
    s = re.sub(r"(?:和|与|及)\s*(?:[，、])", "", s)
    s = re.sub(r"(?:和|与|及)\s*([。！？!?])", r"\1", s)

    # 再移除“语速/口吻/神态动作”类片段（尽量做局部替换，避免整段被删空）。
    # 处理“语速X/语气X/语调X …”这类带修饰的情况。
    s = re.sub(r"(语速|语气|语调)\s*[^，。！？!?]*[，、]?", "", s)
    # 处理明确短语
    for phrase in _DISALLOWED_ROLE_DELIVERY_PHRASES:
        s = s.replace(phrase, "")

    # 清理多余标点与空白，避免变成“性格XX，常提及…”出现多重逗号。
    s = re.sub(r"[，、]\s*[，、]+", "，", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip("，,、 ")
    return s


def is_guidance_stage(stage: dict) -> bool:
    """检测该阶段是否为指导/讲解型（而非问答考核型）。"""
    return detect_interaction_strategy(stage) == "guidance"


def detect_interaction_strategy(stage: dict) -> str:
    """
    识别 A 卡互动策略：
    - guidance: 指导/共情型
    - qa: 问答/考核型

    优先级：
    1) 显式字段覆盖（interaction_strategy/stage_style）
    2) 学科与任务关键词自动识别
    3) 兼容旧逻辑回退
    """
    # 1) 显式覆盖，支持阶段对象人工指定
    override = str(
        stage.get("interaction_strategy", "") or stage.get("stage_style", "")
    ).strip().lower()
    if override in {"guidance", "coach", "coaching", "empathy", "support"}:
        return "guidance"
    if override in {"qa", "exam", "assessment", "questioning"}:
        return "qa"

    # 2) 自动识别：学科 + 任务语义
    text = build_stage_text(stage)
    has_guidance_discipline = any(keyword in text for keyword in _GUIDANCE_DISCIPLINE_KEYWORDS)
    has_qa_discipline = any(keyword in text for keyword in _QA_DISCIPLINE_KEYWORDS)
    has_guidance_task = any(keyword in text for keyword in _GUIDANCE_TASK_HINTS)
    has_qa_task = any(keyword in text for keyword in _QA_TASK_HINTS)

    if (has_guidance_discipline or has_guidance_task) and not (has_qa_discipline or has_qa_task):
        return "guidance"
    if (has_qa_discipline or has_qa_task) and not (has_guidance_discipline or has_guidance_task):
        return "qa"

    # 3) 兼容旧逻辑
    role_task_text = f"{stage.get('role', '')} {stage.get('task', '')}"
    has_guidance = any(keyword in role_task_text for keyword in _GUIDANCE_KEYWORDS)
    if has_guidance and not any(keyword in role_task_text for keyword in _QA_OVERRIDE_KEYWORDS):
        return "guidance"
    return "qa"


def build_stage_text(stage: dict) -> str:
    """拼接阶段文本，用于简单规则判断。"""
    parts = [
        stage.get("title", ""),
        stage.get("description", ""),
        stage.get("role", ""),
        stage.get("task", ""),
        stage.get("content_excerpt", ""),
    ]
    key_points = stage.get("key_points") or []
    if isinstance(key_points, list):
        parts.extend(str(item) for item in key_points if item)
    return " ".join(str(part).strip() for part in parts if str(part).strip())


def needs_follow_up_constraint(stage: dict) -> bool:
    """只有目标明确需要追深说明时，才展示追问类约束。"""
    if is_guidance_stage(stage):
        return False
    text = build_stage_text(stage)
    return any(keyword in text for keyword in _FOLLOW_UP_KEYWORDS)


def split_constraint_items(text: str) -> List[str]:
    """将模型返回的 Constraints 规整成逐条列表。"""
    if not text:
        return []

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    normalized = normalized.replace('""', "")
    normalized = re.sub(r"([。！？；!?])\s*-\s+", r"\1\n- ", normalized)
    normalized = re.sub(r"\n\s*-\s+", "\n- ", normalized)

    items: List[str] = []
    seen = set()
    for line in normalized.split("\n"):
        item = re.sub(r"^[\-*•]\s*", "", line.strip())
        if not item or item in seen:
            continue
        seen.add(item)
        items.append(item)
    return items


def is_generation_only_constraint(item: str) -> bool:
    """过滤只服务于生成过程、不应展示给最终卡片的规则。"""
    return any(pattern.search(item) for pattern in _GENERATION_ONLY_CONSTRAINT_PATTERNS)


def format_constraint_items(items: List[str]) -> str:
    return "\n".join(f"- {item}" for item in items if item)


def create_stage_meta(stage: dict, default_interaction_rounds: int = 5) -> str:
    """创建阶段元数据块。"""
    meta = {
        "stage_name": stage.get("title", ""),
        "description": stage.get("description", ""),
        "interaction_rounds": stage.get("interaction_rounds", default_interaction_rounds),
    }
    return f"<!-- STAGE_META: {json.dumps(meta, ensure_ascii=False)} -->\n"


def build_stage_coverage_hints(stage: dict) -> List[str]:
    """抽取本幕需要覆盖的原文锚点（用于 A 卡覆盖度自检与补强重试）。"""
    coverage_hints: List[str] = []
    stage_key_points = stage.get("key_points") or []
    if isinstance(stage_key_points, list):
        for key_point in stage_key_points:
            if isinstance(key_point, str):
                text = key_point.strip()
                if len(text) >= 2:
                    coverage_hints.append(text[:40])
            if len(coverage_hints) >= 10:
                break

    if len(coverage_hints) < 4:
        excerpt = str(stage.get("content_excerpt") or "").strip()
        if excerpt:
            candidates = re.split(r"[，。；;,.、\n]", excerpt)
            for candidate in candidates:
                text = candidate.strip()
                if 4 <= len(text) <= 30 and text not in coverage_hints:
                    coverage_hints.append(text)
                if len(coverage_hints) >= 10:
                    break
    return coverage_hints


def calc_missing_anchors(result: Any, coverage_hints: List[str]) -> List[str]:
    """计算 A 卡中未显式覆盖的锚点。"""
    if not coverage_hints:
        return []
    combined = " ".join(
        [
            getattr(result, "role_section", "") or "",
            getattr(result, "context_section", "") or "",
            getattr(result, "interaction_section", "") or "",
            getattr(result, "transition_section", "") or "",
        ]
    )
    return [hint for hint in coverage_hints if hint and hint not in combined]


def build_display_constraints(raw_constraints: str, stage: dict) -> str:
    """清理并补齐 A 卡最终展示给用户的 Constraints。"""
    items = [
        item for item in split_constraint_items(raw_constraints)
        if not is_generation_only_constraint(item)
    ]
    guidance_stage = is_guidance_stage(stage)

    if guidance_stage:
        pacing_constraint = "每轮先讲清1-2个步骤或原理，再请学生用一句话复述或确认关键点，不要把整段内容变成连续追问。"
        if not any(("讲" in item and "步骤" in item) or "复述" in item for item in items):
            items.append(pacing_constraint)
    else:
        pacing_constraint = "每轮围绕当前任务推进1-2个问题，避免一次抛出过多问题。"
        if not any("每轮" in item or "问题" in item for item in items):
            items.append(pacing_constraint)

        if needs_follow_up_constraint(stage):
            follow_up_constraint = "当本幕目标明确要求学生说明原因、依据或遗漏项时，再顺势补问一层；不需要时不要为了追问而追问。"
            if not any(
                keyword in item
                for item in items
                for keyword in ("追问", "补问", "依据", "原因", "为什么", "遗漏项")
            ):
                items.append(follow_up_constraint)

    if not items:
        items = [pacing_constraint]

    if not any("150-200词" in item or "不超过250词" in item for item in items):
        items.append(_A_RUNTIME_LENGTH_CONSTRAINT)
    if not any("连续追问2轮" in item or "切换到本幕下一个要点" in item for item in items):
        items.append(_A_ANTI_LOOP_CONSTRAINT)

    return format_constraint_items(items[: max(_MAX_A_CARD_CONSTRAINTS, 5)])


def build_b_display_constraints(use_narrator: bool) -> str:
    """构建 B 卡展示层约束，避免把冗长防跑偏指令写进卡片。"""
    items = (
        _B_CARD_NARRATOR_DISPLAY_CONSTRAINTS
        if use_narrator
        else _B_CARD_SIMPLE_DISPLAY_CONSTRAINTS
    )
    merged = list(items)
    if not any("50-120词" in item or "不超过150词" in item for item in merged):
        merged.append(_B_RUNTIME_LENGTH_CONSTRAINT)
    return format_constraint_items(merged)


def build_ending_display_constraints() -> str:
    """构建结尾卡展示层约束，保持简洁。"""
    return format_constraint_items(list(_ENDING_DISPLAY_CONSTRAINTS))


def format_card_a(result: Any, stage_index: int, stage_meta: str, stage: dict) -> str:
    """格式化 A 类卡片输出。"""
    sections = [stage_meta]

    if getattr(result, "prologue", ""):
        sections.append(format_card_section("Prologue", result.prologue))

    sections.append(format_card_section("Role", result.role_section))
    sections.append(format_card_section("Context", result.context_section))
    sections.append(format_card_section("Interaction", result.interaction_section))
    sections.append(format_card_section("Transition", result.transition_section))
    sections.append(f"当剧情自然进展到转折点时，仅输出：**卡片{stage_index}B**\n")

    if getattr(result, "options_section", ""):
        sections.append(format_card_section("Options", result.options_section))

    constraints = build_display_constraints(
        getattr(result, "constraints_section", "") or "",
        stage,
    )
    sections.append(format_card_section("Constraints", constraints))

    return "\n\n".join(sections)


def format_card_b(result: Any, stage: Optional[dict] = None) -> str:
    """格式化 B 类卡片输出（不再包含显式跳转指令正文）。"""
    sections = []
    use_narrator = getattr(result, "use_narrator", False)
    response_logic_text = _sanitize_b_response_logic_text(
        getattr(result, "output_section", "") or "",
        stage=stage,
    )

    if use_narrator:
        sections.append(format_card_section("Role", result.role_section))
        sections.append(format_card_section("Context", result.context_section))
        sections.append(format_card_section("Response Logic", response_logic_text))
        sections.append(format_card_section("Constraints", build_b_display_constraints(True)))
    else:
        sections.append(format_card_section("Context", result.context_section))
        sections.append(format_card_section("Response Logic", response_logic_text))
        sections.append(format_card_section("Constraints", build_b_display_constraints(False)))

    body = "\n".join(sections)
    return "${previous_dialogue}\n\n" + body


_STYLE_REPLACEMENT_RULES = (
    (re.compile(r"不过"), ("但这里要补一句", "需要注意的是", "另一个关键点是", "同时别忽略")),
    (re.compile(r"那咱们"), ("我们接着", "下面我们", "接下来我们", "我们换个角度")),
    (re.compile(r"很贴合现场"), ("比较贴近现场", "符合现场逻辑", "和现场工况一致")),
    (re.compile(r"得再明确"), ("需要再说具体", "还要补清楚", "要再落细一点")),
    (re.compile(r"回答很贴合[^。！!?]{0,40}[！!]"), ("这个回答抓到关键了。", "这个回答方向是对的。", "这个回答已经接近现场要求。")),
)
_STYLE_AUDIT_PATTERNS = (
    ("不过", re.compile(r"不过")),
    ("那咱们", re.compile(r"那咱们")),
    ("很贴合现场", re.compile(r"很贴合现场")),
    ("得再明确", re.compile(r"得再明确")),
    ("肯定+纠偏模板", re.compile(r"回答很贴合[^。！!?]{0,40}[！!].{0,80}(确实|但是|但)")),
)


def _replace_repeated_style_markers(text: str, usage_state: dict) -> str:
    updated = text
    for pattern, alternatives in _STYLE_REPLACEMENT_RULES:
        matches = list(pattern.finditer(updated))
        if not matches:
            continue
        seen = usage_state.setdefault(pattern.pattern, 0)
        # 第一处保留原样，从第二处开始替换，避免跨卡片重复模板。
        for idx, match in enumerate(matches):
            global_index = seen + idx
            if global_index == 0:
                continue
            replacement = alternatives[(global_index - 1) % len(alternatives)]
            updated = updated[:match.start()] + replacement + updated[match.end():]
            break
        usage_state[pattern.pattern] = seen + len(matches)
    return updated


def review_cross_card_style_diversity(card_blocks: List[str]) -> List[str]:
    """
    上帝视角审查跨卡片风格，降低机械连接词和固定句式重复。
    仅处理 A 卡 Interaction 与 B 卡 Response Logic 段落，避免影响结构字段。
    """
    reviewed: List[str] = []
    usage_state: dict = {}

    for block in card_blocks:
        current = block
        for section_name in ("Interaction", "Response Logic"):
            section_pattern = re.compile(
                rf"(# {re.escape(section_name)}\n)(.*?)(\n# |\Z)",
                re.DOTALL,
            )
            match = section_pattern.search(current)
            if not match:
                continue
            content = match.group(2)
            rewritten = _replace_repeated_style_markers(content, usage_state)
            current = current[:match.start(2)] + rewritten + current[match.end(2):]
        reviewed.append(current)

    return reviewed


def build_style_audit_report(card_blocks: List[str]) -> Dict[str, Any]:
    """
    统计跨卡片高频机械表达，用于生成后审查日志。
    """
    merged_text = "\n".join(card_blocks)
    counts = {
        name: len(pattern.findall(merged_text))
        for name, pattern in _STYLE_AUDIT_PATTERNS
    }
    total_hits = sum(counts.values())
    return {
        "total_hits": total_hits,
        "counts": counts,
    }
