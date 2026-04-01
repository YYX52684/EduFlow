from types import SimpleNamespace

from generators.dspy_utils import (
    post_process_fields,
    reset_positive_feedback_history,
    sanitize_interaction_style,
    select_diverse_phrase,
    should_inject_positive_feedback,
)


def test_select_diverse_phrase_prefers_unused_phrase():
    phrases = ["甲", "乙", "丙"]
    chosen = select_diverse_phrase("same-seed", phrases, recent_phrases=["甲", "乙"])
    assert chosen == "丙"


def test_select_diverse_phrase_is_stable_for_same_seed():
    phrases = ["甲", "乙", "丙", "丁"]
    first = select_diverse_phrase("seed-1", phrases, recent_phrases=["甲"])
    second = select_diverse_phrase("seed-1", phrases, recent_phrases=["甲"])
    assert first == second


def test_should_not_inject_when_positive_feedback_already_exists():
    assert should_inject_positive_feedback("很好，这个判断已经抓住关键了。") is False


def test_post_process_fields_keeps_existing_positive_feedback():
    reset_positive_feedback_history()
    obj = SimpleNamespace(
        interaction_section="很好，这个判断已经抓住关键了。",
        context_section="病房（白天）",
    )

    post_process_fields(
        obj,
        ["interaction_section", "context_section"],
        inject_positive_feedback=True,
    )

    assert obj.interaction_section == "很好，这个判断已经抓住关键了。"
    assert obj.context_section == "病房"


def test_sanitize_interaction_style_removes_hint_and_restatement_tone():
    text = "你提到的这些参数方向是对的（反映配风合理性）。提示：继续说明关键偏差。"
    out = sanitize_interaction_style(text)
    assert "你提到的" not in out
    assert "提示：" not in out
    assert "反映配风合理性" in out


def test_post_process_fields_compresses_long_praise_prefix():
    obj = SimpleNamespace(
        interaction_section="不错，手动开旁路阀稳水位的临时措施很贴合现场应急操作逻辑，改造方案也比较全面。那我们继续看真空联动。",
    )
    post_process_fields(obj, ["interaction_section"], inject_positive_feedback=False)
    assert obj.interaction_section.startswith("这个方向对了。")
