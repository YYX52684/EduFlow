from types import SimpleNamespace

from generators.dspy_utils import (
    post_process_fields,
    reset_positive_feedback_history,
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
