# -*- coding: utf-8 -*-
"""
卡片配置流测试：CARD_DEFAULTS、阶段元数据、ParsedCard 格式、ContentSplitter 字段。
"""
import json
import re
import inspect
from types import SimpleNamespace

from config import CARD_DEFAULTS


def test_card_defaults():
    """CARD_DEFAULTS 应包含抓包确认的字段名。"""
    required_keys = [
        "model_id",
        "history_num",
        "trainer_name",
        "default_interaction_rounds",
    ]
    for key in required_keys:
        assert key in CARD_DEFAULTS, f"缺少 {key}"


def test_training_doc_config_structure():
    """TRAINING_DOC_CONFIG 与能力训练文档生成器约定一致。"""
    from config import TRAINING_DOC_CONFIG

    assert TRAINING_DOC_CONFIG.get("target_total_score") == 100
    titles = TRAINING_DOC_CONFIG.get("section_h2_titles") or []
    assert titles == [
        "任务目标",
        "智能体人设",
        "任务描述",
        "智能体各板块任务要求",
        "评价标准",
    ]
    assert int(TRAINING_DOC_CONFIG.get("max_validation_retries", 0)) >= 0


def test_stage_meta_generation():
    """阶段元数据生成格式正确（STAGE_META 注释 + JSON）。"""
    from generators.dspy_card_orchestrator import DSPyCardGenerator

    stage = {
        "id": 1,
        "title": "Test Stage",
        "description": "This is a test stage description",
        "interaction_rounds": 7,
        "role": "Test Role",
        "task": "Complete test task",
        "key_points": ["Point1", "Point2"],
        "content_excerpt": "Test excerpt",
    }

    generator = DSPyCardGenerator(api_key="test-key-for-unit-test")
    meta_str = generator._create_stage_meta(stage)
    meta_pattern = r"<!--\s*STAGE_META:\s*(\{.*?\})\s*-->"
    match = re.search(meta_pattern, meta_str)
    assert match, "应包含 STAGE_META 注释"
    meta_data = json.loads(match.group(1))
    assert meta_data.get("stage_name")
    assert meta_data.get("description")
    assert meta_data.get("interaction_rounds") == 7


def test_stage_meta_parsing():
    """注入器能正确解析 STAGE_META。"""
    from api_platform.card_injector import CardInjector

    class MockAPIClient:
        pass

    injector = CardInjector(MockAPIClient())
    test_content = """# Card 1A

<!-- STAGE_META: {"stage_name": "Initial Assessment", "description": "Initial patient assessment", "interaction_rounds": 6} -->

# Role
You are patient Zhang...
"""
    meta = injector._extract_stage_meta(test_content)
    assert meta is not None
    assert meta.get("stage_name") == "Initial Assessment"
    assert meta.get("interaction_rounds") == 6


def test_parsed_card_to_a_card_format():
    """ParsedCard.to_a_card_format 合并 LLM 字段与配置默认值。"""
    from api_platform.card_injector import ParsedCard

    card = ParsedCard(
        card_id="1A",
        stage_num=1,
        card_type="A",
        title="Test Card",
        full_content="Test content",
        stage_name="LLM Stage Name",
        stage_description="LLM Description",
        interaction_rounds=8,
    )
    result = card.to_a_card_format()
    assert result["step_name"] == "LLM Stage Name"
    assert result["description"] == "LLM Description"
    assert result["interaction_rounds"] == 8
    assert "model_id" in result or "model_id" in str(result)
    assert result.get("trainer_name") is not None


def test_api_client_create_step_params():
    """PlatformAPIClient.create_step 参数与抓包字段一致。"""
    from api_platform.api_client import PlatformAPIClient

    sig = inspect.signature(PlatformAPIClient.create_step)
    params = list(sig.parameters.keys())
    required = [
        "step_name",
        "llm_prompt",
        "description",
        "interaction_rounds",
        "model_id",
        "history_num",
        "trainer_name",
    ]
    for param in required:
        assert param in params, f"缺少参数 {param}"


def test_content_splitter_prompt_fields():
    """ContentSplitter.SPLIT_PROMPT 包含 description、interaction_rounds。"""
    from generators.content_splitter import ContentSplitter

    prompt = ContentSplitter.SPLIT_PROMPT
    assert "description" in prompt
    assert "interaction_rounds" in prompt


def test_normalize_interaction_text_keeps_structured_paragraphs():
    """Interaction 后处理应保留结构化段落，支持多轮逻辑模板。"""
    from generators.dspy_utils import normalize_interaction_text

    text = "先回应学生当前说法。\n\n再顺势补一句关键提醒。\n\n# Interaction 最后追问一个核心点。"
    normalized = normalize_interaction_text(text)

    assert "\n\n" in normalized
    assert normalized == "先回应学生当前说法。\n\n再顺势补一句关键提醒。\n\n最后追问一个核心点。"


def test_format_card_a_constraints_hide_generation_only_rules():
    """A卡最终 Constraints 不应泄漏生成期要求。"""
    from generators.dspy_card_orchestrator import DSPyCardGenerator

    generator = DSPyCardGenerator(api_key="test-key-for-unit-test")
    stage = {
        "title": "会谈开场建立关系",
        "description": "引导学生完成自我介绍并建立信任",
        "role": "社区老年居民",
        "task": "引导学生完成自我介绍并开始会谈",
        "key_points": ["专业关系建立", "会谈开场"],
        "content_excerpt": "学生需要主动自我介绍并说明来意。",
    }
    result = SimpleNamespace(
        prologue="",
        role_section="你是张大爷。",
        context_section="学生前来与你会谈。",
        interaction_section="你先问对方是谁，再听他说明来意。",
        transition_section="若学生完成自我介绍并说明来意，视为情景进展到转折点。",
        options_section="",
        constraints_section=(
            "- Interaction 必须保持信息密度：至少覆盖3个锚点。\n"
            "- 在实际对话与反馈中，请特别确保围绕以下原文要点展开，不得只作概括性说明。\n"
            "- 涉及英文/代码/长串时，必须提供编号选项，引导学生说编号或简短中文，不要要求朗读原文。\n"
            "- 学生答对时给予具体正向激励，答对后至少追问1次为什么/依据。"
        ),
    )

    card = generator._format_card_a(result, 1, generator._create_stage_meta(stage), stage)
    constraints = card.split("# Constraints\n", 1)[1].strip()

    assert "信息密度" not in constraints
    assert "原文要点" not in constraints
    assert "编号选项" not in constraints
    assert "朗读原文" not in constraints
    assert "至少追问1次" not in constraints
    assert "每轮围绕当前任务推进1-2个问题" in constraints


def test_format_card_a_follow_up_constraint_only_when_needed():
    """只有需要原因/依据类说明的阶段，才补追深约束。"""
    from generators.dspy_card_orchestrator import DSPyCardGenerator

    generator = DSPyCardGenerator(api_key="test-key-for-unit-test")
    base_result = SimpleNamespace(
        prologue="",
        role_section="你是带教老师。",
        context_section="学生正在与你交流。",
        interaction_section="你先听学生回答，再继续推进当前任务。",
        transition_section="若学生达到本幕要求，视为情景进展到转折点。",
        options_section="",
        constraints_section="- 保持自然口语，避免机械连接词。",
    )

    general_stage = {
        "title": "建立初步关系",
        "description": "完成开场交流",
        "role": "带教老师",
        "task": "让学生完成自我介绍并进入会谈",
        "key_points": ["自我介绍", "建立信任"],
        "content_excerpt": "学生先做自我介绍，再说明来意。",
    }
    follow_up_stage = {
        "title": "分析原因与依据",
        "description": "要求学生说明判断依据",
        "role": "带教老师",
        "task": "请学生分析原因并说明依据",
        "key_points": ["原因分析", "说明依据"],
        "content_excerpt": "学生需要说清判断理由和依据。",
    }

    general_card = generator._format_card_a(
        base_result,
        1,
        generator._create_stage_meta(general_stage),
        general_stage,
    )
    follow_up_card = generator._format_card_a(
        base_result,
        1,
        generator._create_stage_meta(follow_up_stage),
        follow_up_stage,
    )

    general_constraints = general_card.split("# Constraints\n", 1)[1].strip()
    follow_up_constraints = follow_up_card.split("# Constraints\n", 1)[1].strip()

    assert "说明原因、依据或遗漏项" not in general_constraints
    assert "说明原因、依据或遗漏项" in follow_up_constraints


def test_card_a_module_routes_guidance_stages_to_guidance_signature(monkeypatch):
    """A卡模块应按 is_guidance 选择问答型或指导型 signature。"""
    from generators.dspy_card_modules import CardAGeneratorModule

    module = CardAGeneratorModule()
    call_args = {"qa": None, "guidance": None}

    def make_result(role_text: str) -> SimpleNamespace:
        return SimpleNamespace(
            role_section=role_text,
            context_section="学生正在与你交流。",
            interaction_section="你继续推进当前任务。",
            transition_section="若学生达到要求，视为情景进展到转折点。",
            constraints_section="- 保持自然口语。",
            options_section="",
        )

    def qa_stub(**kwargs):
        call_args["qa"] = kwargs
        return make_result("问答分支")

    def guidance_stub(**kwargs):
        call_args["guidance"] = kwargs
        return make_result("指导分支")

    monkeypatch.setattr(module, "generate_card", qa_stub)
    monkeypatch.setattr(module, "generate_guidance_card", guidance_stub)

    qa_result = module.forward(
        full_script="测试剧本全文",
        stage_title="问答阶段",
        npc_role="带教老师",
        scene_goal="请学生说明判断依据",
        key_points="判断依据, 关键风险",
        content_excerpt="学生需要说明判断依据。",
        is_guidance=False,
        include_prologue=False,
    )
    guidance_result = module.forward(
        full_script="测试剧本全文",
        stage_title="指导阶段",
        npc_role="带教老师",
        scene_goal="先讲解步骤再让学生复述",
        key_points="操作步骤, 风险点",
        content_excerpt="老师先讲解，再让学生复述。",
        is_guidance=True,
        include_prologue=False,
    )

    assert qa_result.role_section == "问答分支"
    assert guidance_result.role_section == "指导分支"
    assert "next_card_id" not in call_args["qa"]
    assert "next_card_id" not in call_args["guidance"]
    assert "stage_index" not in call_args["qa"]
    assert "stage_index" not in call_args["guidance"]
    assert "total_stages" not in call_args["qa"]
    assert "total_stages" not in call_args["guidance"]


def test_card_b_module_does_not_require_transition_section(monkeypatch):
    """B卡模块不应再依赖模型返回 transition_section。"""
    from generators.dspy_card_modules import CardBGeneratorModule

    module = CardBGeneratorModule()
    captured = {}

    def simple_stub(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            context_section="先将前文收束到当前情景中的具体落点，再带出下一话题。",
            output_section="嗯，这一点你已经说到了，我们接着往下聊。",
        )

    monkeypatch.setattr(module, "generate_simple", simple_stub)

    result = module.forward(
        full_script="测试剧本全文",
        current_stage_title="阶段一",
        current_stage_goal="回应后带出下一话题",
        current_stage_key_points="关键术语, 风险点",
        current_stage_excerpt="学生上一轮已经提到关键术语。",
        current_stage_role="带教老师",
        next_stage_title="阶段二",
        next_stage_role="带教老师",
        is_last_stage=False,
    )

    assert result.context_section.startswith("先将前文收束到当前情景中的具体落点")
    assert result.output_section.startswith("嗯，这一点你已经说到了")
    assert "full_script" not in captured
    assert "next_card_id" not in captured
    assert "stage_index" not in captured
    assert "total_stages" not in captured
    assert "is_last_stage" not in captured


def test_format_card_b_constraints_are_compact():
    """B卡最终 Constraints 应压缩为少量必要规则。"""
    from generators.dspy_card_orchestrator import DSPyCardGenerator

    generator = DSPyCardGenerator(api_key="test-key-for-unit-test")
    result = SimpleNamespace(
        context_section="先将前文收束到当前情景中的具体落点，再带出下一话题。",
        output_section="嗯，你这话我听明白了，我们接着往下聊。",
        use_narrator=False,
    )

    card = generator._format_card_b(result, 1, 3)
    constraints = card.split("# Constraints\n", 1)[1].strip()

    assert "不要做评分式总结" not in constraints
    assert "严禁出戏" not in constraints
    assert "控制输出长度" not in constraints
    assert "优先基于 `${previous_dialogue}` 最近1-2轮回应" in constraints
    assert "流程话术" in constraints


def test_format_card_b_rewrites_static_template_to_dynamic_output():
    """B卡 Response Logic 应去静态模板并转为动态响应规则。"""
    from generators import dspy_card_helpers as helpers

    anchor_term = "通用锚点术语"
    result = SimpleNamespace(
        context_section="根据上一轮回答继续推进。",
        output_section="你在回答中对核心系统有一定阐述，不过还可以更深入些。接下来，我们可以思考下一步。",
        use_narrator=False,
    )
    stage = {"key_points": [anchor_term]}
    card = helpers.format_card_b(result, stage=stage)
    response_logic = card.split("# Response Logic\n", 1)[1].split("\n\n# Constraints", 1)[0].strip()

    assert "有一定阐述" not in response_logic
    assert "还可以更深入" not in response_logic
    assert "接下来，我们可以思考" not in response_logic
    assert anchor_term in response_logic or "${previous_dialogue}" in response_logic
    assert "锚定" in response_logic
    assert "推进" in response_logic


def test_render_transition_prompt_adds_history_priority_block():
    """B卡渲染 prompt 时应注入“对话历史优先规则”。"""
    from simulator.card_loader import CardData

    card = CardData(
        card_id="1B",
        stage_num=1,
        card_type="B",
        title="卡片1B",
        transition_prompt="${previous_dialogue}\n\n# Response Logic\n继续推进",
    )
    rendered = card.render_transition_prompt("## 最后一轮重点\n学生最后一轮回答: 参数偏高")
    assert "对话历史优先规则" in rendered
    assert "学生最后一轮回答" in rendered


def test_build_ending_display_constraints_are_compact():
    """结尾卡展示层 Constraints 应避免冗长护栏。"""
    from generators.dspy_card_orchestrator import DSPyCardGenerator

    generator = DSPyCardGenerator(api_key="test-key-for-unit-test")
    constraints = generator._build_ending_display_constraints()

    assert "本环节结束" not in constraints
    assert "严禁使用括号" not in constraints
    assert "150字以内" not in constraints
    assert "只做这一轮自然收尾" in constraints


def test_detect_interaction_strategy_with_override_and_auto_rules():
    """互动策略应支持显式覆盖与学科语义自动识别。"""
    from generators.dspy_card_helpers import detect_interaction_strategy

    explicit_guidance = {
        "title": "任意标题",
        "task": "这里即便有分析依据，也应由显式策略覆盖",
        "interaction_strategy": "guidance",
    }
    auto_guidance = {
        "title": "社工访谈建立关系",
        "role": "社区社工",
        "task": "通过同理倾听和共情回应，帮助来访者表达感受并建立信任",
    }
    auto_qa = {
        "title": "工程故障诊断",
        "role": "机械工程师",
        "task": "请学生说明判断依据、关键参数和风险点",
    }

    assert detect_interaction_strategy(explicit_guidance) == "guidance"
    assert detect_interaction_strategy(auto_guidance) == "guidance"
    assert detect_interaction_strategy(auto_qa) == "qa"


def test_transition_anchor_keyword_extraction_and_enforcement():
    """B卡强历史锚定：应从最近学生回复提取关键词并强制命中。"""
    from simulator.session_runner import SessionRunner, SessionConfig, DialogueTurn

    runner = SessionRunner(SessionConfig())
    runner.log = SimpleNamespace(
        dialogue=[
            DialogueTurn(turn_number=1, card_id="1A", speaker="student", content="我认为空气预热器漏风会抬高排烟温度。"),
            DialogueTurn(turn_number=2, card_id="1A", speaker="npc", content="继续说参数影响。"),
        ]
    )
    card = SimpleNamespace(card_id="1A")
    keywords = runner._extract_recent_student_keywords(card)
    joined = " ".join(keywords)
    assert "空气预热器" in joined or "排烟温度" in joined

    out = "我们先进入下一步。"
    forced = runner._force_anchor_into_transition(out, keywords)
    assert any(k in forced for k in keywords)
