"""
DSPy 优化封装

使用闭环仿真 + 内部评估（simulator.evaluator）作为唯一 metric，
对卡片生成程序进行 BootstrapFewShot / MIPRO 优化。
"""

import os
import time
from typing import List, Dict, Any, Optional, Callable

import dspy
from .dspy_card_generator import (
    DSPyCardGenerator,
    CardAGeneratorModule,
    CardBGeneratorModule,
    _optimizer_context,
)


def make_card_generator_program(
    api_key: Optional[str] = None,
    model_type: Optional[str] = None,
) -> dspy.Module:
    """
    构建一个 dspy.Module，对单条样本 (full_script, stages) 生成整份卡片并返回 Prediction(cards=...)。
    供 BootstrapFewShot 等优化器作为 student 使用。
    model_type: "doubao" | "deepseek"，与其它功能一致；默认使用 config.DEFAULT_MODEL_TYPE。
    """
    if model_type is None:
        from config import DEFAULT_MODEL_TYPE
        model_type = DEFAULT_MODEL_TYPE

    class CardGeneratorProgram(dspy.Module):
        def __init__(self):
            super().__init__()
            self._generator = DSPyCardGenerator(api_key=api_key, model_type=model_type)

        def forward(self, full_script: str, stages: List[Dict[str, Any]]) -> dspy.Prediction:
            cards = self._generator.generate_all_cards(stages, full_script)
            return dspy.Prediction(cards=cards)

    return CardGeneratorProgram()


def run_bootstrap_optimizer(
    trainset: List[Dict[str, Any]],
    output_cards_path: str,
    export_path: str,
    export_config: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    model_type: Optional[str] = None,
    max_bootstrapped_demos: int = 4,
    max_labeled_demos: int = 16,
    max_rounds: int = 1,
    metric_threshold: Optional[float] = None,
    use_auto_eval: bool = True,
    persona_id: str = "excellent",
    persona_ids: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> dspy.Module:
    """
    使用 BootstrapFewShot 优化卡片生成程序。

    当前仅支持闭环模式：始终通过仿真 + 内部评估获取分数，
    默认三档人设（优秀/一般/较差）并行评估取均值。

    Args:
        trainset: 样本列表，每项含 full_script 与 stages（可为 dspy.Example 或 dict）。
        output_cards_path: 每轮生成卡片写入的路径。
        export_path: 闭环评估报告导出路径（JSON/Markdown）。
        export_config: 预留参数（当前闭环模式下未使用，可传 None）。
        api_key: API 密钥（可选，不传则用 config 中对应模型的 key）。
        model_type: "doubao" | "deepseek"，与其它功能一致。
        max_bootstrapped_demos: 最大 bootstrap 示例数。
        max_labeled_demos: 最大标注示例数。
        max_rounds: bootstrap 轮数。
        metric_threshold: 接受 bootstrap 示例的分数阈值（可选）。

    Returns:
        优化后的 dspy.Module（CardGeneratorProgram）。
    """
    program = make_card_generator_program(api_key=api_key, model_type=model_type)
    dspy.configure(lm=program._generator.lm)

    from .closed_loop import make_auto_metric
    total_est = max(1, len(trainset) * max_rounds * 2)  # 粗略估计评估次数
    ids = persona_ids if persona_ids else ["excellent", "average", "struggling"]
    metric_fn = make_auto_metric(
        output_cards_path,
        export_path,
        export_config=export_config,
        api_key=api_key,
        model_type=model_type,
        persona_id=persona_id,
        persona_ids=ids,
        prompt_user=True,
        progress_callback=progress_callback,
        total_estimate=total_est,
    )

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
    _optimizer_context.running = True
    try:
        compiled = optimizer.compile(program, trainset=examples)
        return compiled
    finally:
        _optimizer_context.running = False


def run_mipro_optimizer(
    trainset: List[Dict[str, Any]],
    devset: Optional[List[Dict[str, Any]]],
    output_cards_path: str,
    export_path: str,
    export_config: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    model_type: Optional[str] = None,
    num_candidates: int = 10,
    init_temperature: float = 1.0,
    verbose: bool = False,
    num_threads: int = 1,
    use_auto_eval: bool = True,
    persona_id: str = "excellent",
    persona_ids: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    **mipro_kwargs
) -> dspy.Module:
    """
    使用 MIPROv2 优化卡片生成程序。

    始终使用闭环模式：基于仿真 + 内部评估结果打分，
    默认三档人设并行评估取均值。

    MIPRO (Multipurpose Instruction PRoposal Optimizer) 通过以下方式工作：
    1. 分析训练集中的成功案例
    2. 提出指令改进建议
    3. 使用贝叶斯优化选择最佳的指令组合

    相比 BootstrapFewShot，MIPRO 会同时优化：
    - 指令（instructions）
    - 示例（demonstrations）

    Args:
        trainset: 训练样本列表。
        devset: 验证样本列表（用于评估候选指令）。
        output_cards_path: 每轮生成卡片写入的路径。
        export_path: 闭环评估报告导出路径。
        export_config: 预留参数（当前闭环模式下未使用，可传 None）。
        api_key: LLM API 密钥。
        num_candidates: 候选指令集数量（越多计算成本越高）。
        init_temperature: 初始采样温度。
        verbose: 是否打印详细日志。
        num_threads: 并行评估的线程数。

    Returns:
        优化后的 dspy.Module（CardGeneratorProgram）。
    """
    program = make_card_generator_program(api_key=api_key, model_type=model_type)
    dspy.configure(lm=program._generator.lm)

    from .closed_loop import make_auto_metric
    total_est = max(1, len(trainset) * 4)  # MIPRO 迭代次数难以精确预估
    ids = persona_ids if persona_ids else ["excellent", "average", "struggling"]
    metric_fn = make_auto_metric(
        output_cards_path,
        export_path,
        export_config=export_config,
        api_key=api_key,
        model_type=model_type,
        persona_id=persona_id,
        persona_ids=ids,
        prompt_user=True,
        progress_callback=progress_callback,
        total_estimate=total_est,
    )

    # 转换数据集
    train_examples = []
    for ex in trainset:
        if isinstance(ex, dspy.Example):
            train_examples.append(ex)
        else:
            train_examples.append(
                dspy.Example(full_script=ex["full_script"], stages=ex["stages"])
                .with_inputs("full_script", "stages")
            )

    dev_examples = None
    if devset:
        dev_examples = []
        for ex in devset:
            if isinstance(ex, dspy.Example):
                dev_examples.append(ex)
            else:
                dev_examples.append(
                    dspy.Example(full_script=ex["full_script"], stages=ex["stages"])
                    .with_inputs("full_script", "stages")
                )

    # 使用 MIPROv2 优化器（auto 模式默认 "light"，与 num_candidates 互斥，不传 num_candidates）
    # num_threads 固定为 1：dspy.settings 为线程局部，多线程会导致 "can only be changed by the thread that initially configured it"
    optimizer = dspy.MIPROv2(
        metric=metric_fn,
        init_temperature=init_temperature,
        verbose=verbose,
        num_threads=1,
    )

    _optimizer_context.running = True
    try:
        compiled = optimizer.compile(
            program,
            trainset=train_examples,
            valset=dev_examples,
        )
        return compiled
    finally:
        _optimizer_context.running = False


def run_optimize_dspy(
    trainset_path: str,
    devset_path: Optional[str],
    output_cards_path: str,
    export_path: str,
    export_config: Optional[Dict[str, Any]] = None,
    optimizer_type: str = "bootstrap",
    api_key: Optional[str] = None,
    model_type: Optional[str] = None,
    max_rounds: int = 1,
    max_bootstrapped_demos: int = 4,
    use_auto_eval: bool = True,
    persona_id: str = "excellent",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    **mipro_kwargs
) -> dspy.Module:
    """
    统一入口：从 JSON 加载 trainset（及可选 devset），运行优化器，返回优化后的程序。

    当前始终使用闭环模式（仿真 + 内部评估）作为优化指标，
    API Key 与 model_type 与其它功能一致（doubao / deepseek）。
    """
    from .trainset_builder import load_trainset
    from config import DEFAULT_MODEL_TYPE, DOUBAO_API_KEY, DEEPSEEK_API_KEY

    model_type = model_type or DEFAULT_MODEL_TYPE
    if api_key is None:
        api_key = DOUBAO_API_KEY if model_type == "doubao" else DEEPSEEK_API_KEY

    trainset = load_trainset(trainset_path)
    if not trainset:
        raise ValueError(f"trainset 为空: {trainset_path}")
    devset = load_trainset(devset_path) if devset_path and os.path.isfile(devset_path) else None

    if optimizer_type == "bootstrap":
        return run_bootstrap_optimizer(
            trainset=trainset,
            output_cards_path=output_cards_path,
            export_path=export_path,
            export_config=export_config,
            api_key=api_key,
            model_type=model_type,
            max_bootstrapped_demos=max_bootstrapped_demos,
            max_rounds=max_rounds,
            use_auto_eval=use_auto_eval,
            persona_id=persona_id,
            progress_callback=progress_callback,
        )
    elif optimizer_type == "mipro":
        return run_mipro_optimizer(
            trainset=trainset,
            devset=devset,
            output_cards_path=output_cards_path,
            export_path=export_path,
            export_config=export_config,
            api_key=api_key,
            model_type=model_type,
            use_auto_eval=use_auto_eval,
            persona_id=persona_id,
            progress_callback=progress_callback,
            **mipro_kwargs
        )
    else:
        raise ValueError(f"不支持的 optimizer_type: {optimizer_type}，请使用 'bootstrap' 或 'mipro'")
