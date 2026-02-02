"""
DSPy 优化封装
使用外部评估导出文件作为 metric，对卡片生成程序进行 BootstrapFewShot / MIPRO 优化。
"""

import os
import time
from typing import List, Dict, Any, Optional, Callable

import dspy
from .dspy_card_generator import DSPyCardGenerator
from .external_metric import get_score_from_export, load_config_from_dict


def make_card_generator_program(api_key: Optional[str] = None) -> dspy.Module:
    """
    构建一个 dspy.Module，对单条样本 (full_script, stages) 生成整份卡片并返回 Prediction(cards=...)。
    供 BootstrapFewShot 等优化器作为 student 使用。
    """
    class CardGeneratorProgram(dspy.Module):
        def __init__(self):
            super().__init__()
            self._generator = DSPyCardGenerator(api_key=api_key)

        def forward(self, full_script: str, stages: List[Dict[str, Any]]) -> dspy.Prediction:
            cards = self._generator.generate_all_cards(stages, full_script)
            return dspy.Prediction(cards=cards)

    return CardGeneratorProgram()


def make_metric(
    output_cards_path: str,
    export_path: str,
    export_config: Optional[Dict[str, Any]] = None,
    wait_seconds: float = 0,
    prompt_user: bool = True,
) -> Callable:
    """
    返回 DSPy 所需的 metric(example, pred, trace=None) -> score。

    行为：将 pred.cards 写入 output_cards_path，然后从 export_path 读取外部评估分数并返回。
    若 export 文件不存在，可等待 wait_seconds 后重试，或返回 0（由 export_config 控制）。

    Args:
        output_cards_path: 生成卡片写入的路径（每次评估会覆盖）。
        export_path: 外部评估导出文件路径。
        export_config: 传给 get_score_from_export 的配置（parser、parser_kwargs 等）。
        wait_seconds: 写入卡片后等待秒数再读导出文件（可选）。
        prompt_user: 是否在写入后打印提示，让用户到外部平台评估并导出。
    """
    export_config = export_config or {}
    opts = load_config_from_dict({
        **export_config,
        "export_file_path": export_path,
    })

    def metric(example, pred, trace=None):
        cards = getattr(pred, "cards", None)
        if cards is None:
            return 0.0
        path = os.path.abspath(output_cards_path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(cards)
        if prompt_user:
            print(f"\n  [metric] 已写入卡片到: {path}")
            print("  [metric] 请使用外部平台对上述卡片进行评估，并将结果导出到:", os.path.abspath(export_path))
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        return get_score_from_export(export_path=export_path, **opts)

    return metric


def run_bootstrap_optimizer(
    trainset: List[Dict[str, Any]],
    output_cards_path: str,
    export_path: str,
    export_config: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    max_bootstrapped_demos: int = 4,
    max_labeled_demos: int = 16,
    max_rounds: int = 1,
    metric_threshold: Optional[float] = None,
) -> dspy.Module:
    """
    使用 BootstrapFewShot 优化卡片生成程序。

    Args:
        trainset: 样本列表，每项含 full_script 与 stages（可为 dspy.Example 或 dict）。
        output_cards_path: 每轮生成卡片写入的路径。
        export_path: 外部评估导出文件路径。
        export_config: 外部指标解析配置。
        api_key: DeepSeek API 密钥。
        max_bootstrapped_demos: 最大 bootstrap 示例数。
        max_labeled_demos: 最大标注示例数。
        max_rounds: bootstrap 轮数。
        metric_threshold: 接受 bootstrap 示例的分数阈值（可选）。

    Returns:
        优化后的 dspy.Module（CardGeneratorProgram）。
    """
    program = make_card_generator_program(api_key=api_key)
    metric_fn = make_metric(output_cards_path, export_path, export_config, prompt_user=True)

    # 将 dict 转为 dspy.Example 以便优化器使用
    examples = []
    for ex in trainset:
        if isinstance(ex, dspy.Example):
            examples.append(ex)
        else:
            examples.append(dspy.Example(full_script=ex["full_script"], stages=ex["stages"]).with_inputs("full_script", "stages"))

    optimizer = dspy.BootstrapFewShot(
        metric=metric_fn,
        metric_threshold=metric_threshold,
        max_bootstrapped_demos=max_bootstrapped_demos,
        max_labeled_demos=max_labeled_demos,
        max_rounds=max_rounds,
    )
    compiled = optimizer.compile(program, trainset=examples)
    return compiled


def run_optimize_dspy(
    trainset_path: str,
    devset_path: Optional[str],
    output_cards_path: str,
    export_path: str,
    export_config: Optional[Dict[str, Any]] = None,
    optimizer_type: str = "bootstrap",
    api_key: Optional[str] = None,
    max_rounds: int = 1,
    max_bootstrapped_demos: int = 4,
) -> dspy.Module:
    """
    统一入口：从 JSON 加载 trainset（及可选 devset），运行优化器，返回优化后的程序。

    Args:
        trainset_path: trainset JSON 文件路径。
        devset_path: 可选；若提供则用 devset 做评估（当前实现仍用 trainset 做 bootstrap，后续可扩展）。
        output_cards_path: 生成卡片输出路径。
        export_path: 外部评估导出文件路径。
        export_config: 外部指标配置。
        optimizer_type: "bootstrap" 或 "mipro"（mipro 可后续实现）。
        api_key: API 密钥。
        max_rounds: bootstrap 轮数。
        max_bootstrapped_demos: 最大 bootstrap 示例数。

    Returns:
        优化后的 dspy.Module。
    """
    from .trainset_builder import load_trainset

    trainset = load_trainset(trainset_path)
    if not trainset:
        raise ValueError(f"trainset 为空: {trainset_path}")
    devset = load_trainset(devset_path) if devset_path and os.path.isfile(devset_path) else None
    if devset is not None and len(devset) > 0:
        # 当前用 devset 第一条做「程序级」评估时的生成；BootstrapFewShot 仍用 trainset
        pass

    if optimizer_type == "bootstrap":
        return run_bootstrap_optimizer(
            trainset=trainset,
            output_cards_path=output_cards_path,
            export_path=export_path,
            export_config=export_config,
            api_key=api_key,
            max_bootstrapped_demos=max_bootstrapped_demos,
            max_rounds=max_rounds,
        )
    if optimizer_type == "mipro":
        raise NotImplementedError("MIPROv2 暂未实现，请使用 optimizer_type='bootstrap'")
    raise ValueError(f"不支持的 optimizer_type: {optimizer_type}")
