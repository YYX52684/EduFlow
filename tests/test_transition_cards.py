from simulator.card_loader import CardData, LocalCardLoader


def test_transition_card_keeps_full_prompt_sections():
    content = """# 卡片1B

${previous_dialogue}

# Role
你是词汇助教。

# Context
先回应最后一轮，再过渡。

# Response Logic
锚定：先接住学生最后一轮回答，再带到下一题。

# Constraints
- 简洁自然。
"""
    loader = LocalCardLoader()
    cards = loader.parse_markdown_content(content)

    assert len(cards) == 1
    card = cards[0]
    assert "${previous_dialogue}" in card.transition_prompt
    assert "# Role" in card.transition_prompt
    assert "# Response Logic" in card.transition_prompt
    assert card.response_logic == "锚定：先接住学生最后一轮回答，再带到下一题。"


def test_render_transition_prompt_replaces_previous_dialogue():
    card = CardData(
        card_id="1B",
        stage_num=1,
        card_type="B",
        title="卡片1B",
        transition_prompt="${previous_dialogue}\n\n# Role\n你是词汇助教。",
    )

    rendered = card.render_transition_prompt("学生最后一轮回答: bacterium。")

    assert "${previous_dialogue}" not in rendered
    assert "学生最后一轮回答: bacterium。" in rendered
    assert "# Role" in rendered


def test_render_transition_prompt_prepends_dialogue_when_placeholder_missing():
    card = CardData(
        card_id="1B",
        stage_num=1,
        card_type="B",
        title="卡片1B",
        transition_prompt="# Role\n你是词汇助教。",
    )

    rendered = card.render_transition_prompt("学生最后一轮回答: bacterium。")

    assert rendered.startswith("学生最后一轮回答: bacterium。")
    assert "# Role" in rendered
