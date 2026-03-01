# -*- coding: utf-8 -*-
"""测试 Interaction 动作描写清洗逻辑"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from simulator.card_loader import LocalCardLoader


def test_strip_interaction():
    text = (
        '你微笑着看向学生，说道："经过前面几个阶段的讨论，现在请你概述一下为MDMS设计的口服制剂初步方案，包括剂型和核心处方策略。"'
        '等学生回答后，你接着问："那你处方中必备的3-4类关键辅料有哪些，它们各自的主要功能是什么呢？" '
        "很好，这个回答很具体，继续保持。"
    )
    out = LocalCardLoader._strip_interaction_stage_directions(text)
    assert "你微笑着" not in out, "应去掉动作描写"
    assert "说道" not in out, "应去掉说道"
    assert "经过前面几个阶段的讨论" in out, "应保留台词内容"
    assert "接着可问" in out or "那你处方" in out, "应保留或改写追问"
    print("OK:", out[:150])


if __name__ == "__main__":
    test_strip_interaction()
