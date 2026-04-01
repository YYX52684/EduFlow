# -*- coding: utf-8 -*-
"""能力训练文档：配置、规范化与校验。"""
from generators.dspy_training_doc_helpers import (
    normalize_training_doc_markdown,
    validate_training_doc_markdown,
)
from generators.dspy_training_doc_orchestrator import TrainingDocGenerator


def test_training_doc_config_keys():
    from config import TRAINING_DOC_CONFIG

    assert TRAINING_DOC_CONFIG.get("generator_type")
    assert TRAINING_DOC_CONFIG.get("target_total_score") == 100
    assert len(TRAINING_DOC_CONFIG.get("section_h2_titles", [])) == 5


def test_normalize_replaces_ppt_terms():
    raw = "请结合PPT第3页与幻灯片说明操作。"
    out = normalize_training_doc_markdown(raw)
    assert "ppt" not in out.lower()
    assert "幻灯片" not in out
    assert "所给图片" in out


def test_validate_accepts_wellformed_markdown():
    doc = """# 《机电基础》测试能力训练文档

## 任务目标

本次实训旨在让学员在模拟工位中完成测试操作，能结合所给图片识别关键部件，按规范口述检查顺序与安全要点，形成可考核的行为化表述；完成后能说明常见误操作及纠正思路，达到岗位初训过关标准。以上为压缩示例，实际生成应更贴近课程材料。

## 智能体人设

测试工程师陈老师，性格严谨、表达清晰，沟通风格偏实操口令式，善于用追问定位遗漏；拥有多年设备点检培训经验。

## 任务描述

智能体将分板块引导学员完成测试流程，采用指令引导、学员作答、细节追问、纠错确认与步骤进阶相结合的方式进行互动。

## 智能体各板块任务要求

### 工位确认板块

场景设定：结合所给图片确认工位状态与工具摆放。智能体下发清点指令并追问安全确认要点；学员口述动作与验收点。

### 核心操作板块

场景设定：结合所给图片完成关键步骤表述。智能体纠错并推进下一动作；学员按顺序复述。

### 各板块互动话术示例

| 实训板块 | 互动环节 | 智能体话术 | 学员作答示例 |
| --- | --- | --- | --- |
| 工位确认 | 指令引导 | 请结合所给图片说明工具清点顺序。 | 先清点扳手与抹布，再确认急停状态。 |
| 核心操作 | 追问 | 结合所给图片，关键尺寸如何自检？ | 我用目视与简单测量确认在允许范围内。 |

## 评价标准

本次评价总分100分，80分及以上为达标。

| 评分项 | 评分描述 | 对应分值 | 扣分标准 |
| --- | --- | --- | --- |
| 工位确认 | 完整准确 | 50分 | 遗漏关键项扣5分 |
| 核心操作 | 完整准确 | 50分 | 表述错误扣5分 |
"""
    ok, errors = validate_training_doc_markdown(doc)
    assert ok, errors


def test_validate_rejects_wrong_h2_order():
    doc = """# T

## 任务描述

x

## 任务目标

y
"""
    ok, errors = validate_training_doc_markdown(doc)
    assert not ok
    assert any("二级标题" in e for e in errors)


def test_training_doc_generator_init_with_test_key():
    gen = TrainingDocGenerator(api_key="test-key-for-unit-test")
    assert gen.lm is not None
