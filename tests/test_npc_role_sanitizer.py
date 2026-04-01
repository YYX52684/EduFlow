# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generators.dspy_card_helpers import sanitize_npc_role_text


def test_sanitize_npc_role_removes_emotion_and_delivery_phrases():
    raw = (
        "你是张大爷，今年60岁，原是HR村村民，现在已完成村改居，迁入新型城市社区。"
        "你曾是村里传统舞龙活动的带头人，舞龙技艺娴熟，长期组织排练和传承舞龙文化，在村里备受尊重。"
        "村改居后，新社区缺乏舞龙场地和伙伴，你感到失落和孤独。"
        "你性格温和实在，沟通时口语化、语速平缓，常提及过去村里舞龙的热闹场景。"
    )
    out = sanitize_npc_role_text(raw)

    # 情绪词汇不应出现在输入提示词里
    assert "失落" not in out
    assert "孤独" not in out
    # 动作/神态/口吻描写（示例中的语速平缓）不应出现在输入提示词里
    assert "语速平缓" not in out
    # 重要经历类事实应保留
    assert "舞龙技艺娴熟" in out
    assert "传承舞龙文化" in out
    # 同一句里的事实片段应尽量保留
    assert "舞龙场地" in out


def test_sanitize_npc_role_keeps_non_emotion_facts():
    raw = "他曾带队巡检设备，掌握关键步骤与禁忌。并且很开心，但这句话不应保留。"
    out = sanitize_npc_role_text(raw)
    assert "开心" not in out
    assert "带队巡检设备" in out
    assert "关键步骤" in out

