"""
DSPy 优化封装
使用外部评估导出文件作为 metric，对卡片生成程序进行 BootstrapFewShot / MIPRO 优化。

支持闭环模式（use_auto_eval=True）：以仿真+评估替代外部平台人工评估。
"""

import os
import time
from typing import List, Dict, Any, Optional, Callable

import dspy


def build_export_config(export_path: str, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """根据导出文件路径与 DSPY_OPTIMIZER_CONFIG 构建 get_score_from_export 所需的 export_config。"""
    cfg = cfg or {}
    ext = os.path.splitext(export_path)[1].lower()
    parser = "md" if ext in (".md", ".markdown") else cfg.get("parser", "json")
    return {
        "parser": parser,
        "json_score_key": cfg.get("json_score_key", "total_score"),
        "csv_score_column": cfg.get("csv_score_column"),
    }
from .dspy_card_generator import DSPyCardGenerator, CardAGeneratorModule, CardBGeneratorModule
from .external_metric import get_score_from_export, load_config_from_dict


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
    model_type: Optional[str] = None,
    max_bootstrapped_demos: int = 4,
    max_labeled_demos: int = 16,
    max_rounds: int = 1,
    metric_threshold: Optional[float] = None,
    use_auto_eval: bool = False,
    persona_id: str = "excellent",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> dspy.Module:
    """
    使用 BootstrapFewShot 优化卡片生成程序。

    Args:
        trainset: 样本列表，每项含 full_script 与 stages（可为 dspy.Example 或 dict）。
        output_cards_path: 每轮生成卡片写入的路径。
        export_path: 外部评估导出文件路径。
        export_config: 外部指标解析配置。
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

    if use_auto_eval:
        from .closed_loop import make_auto_metric
        total_est = max(1, len(trainset) * max_rounds * 2)  # 粗略估计评估次数
        metric_fn = make_auto_metric(
            output_cards_path,
            export_path,
            export_config=export_config,
            api_key=api_key,
            model_type=model_type,
            persona_id=persona_id,
            prompt_user=True,
            progress_callback=progress_callback,
            total_estimate=total_est,
        )
    else:
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
    use_auto_eval: bool = False,
    persona_id: str = "excellent",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    **mipro_kwargs
) -> dspy.Module:
    """
    使用 MIPROv2 优化卡片生成程序。

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
        export_path: 外部评估导出文件路径。
        export_config: 外部指标解析配置。
        api_key: DeepSeek API 密钥。
        num_candidates: 候选指令集数量（越多计算成本越高）。
        init_temperature: 初始采样温度。
        verbose: 是否打印详细日志。
        num_threads: 并行评估的线程数。

    Returns:
        优化后的 dspy.Module（CardGeneratorProgram）。
    """
    program = make_card_generator_program(api_key=api_key, model_type=model_type)
    dspy.configure(lm=program._generator.lm)

    if use_auto_eval:
        from .closed_loop import make_auto_metric
        total_est = max(1, len(trainset) * 4)  # MIPRO 迭代次数难以精确预估
        metric_fn = make_auto_metric(
            output_cards_path,
            export_path,
            export_config=export_config,
            api_key=api_key,
            model_type=model_type,
            persona_id=persona_id,
            prompt_user=True,
            progress_callback=progress_callback,
            total_estimate=total_est,
        )
    else:
        metric_fn = make_metric(output_cards_path, export_path, export_config, prompt_user=True)

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

    compiled = optimizer.compile(
        program,
        trainset=train_examples,
        valset=dev_examples,
    )
    return compiled


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
    use_auto_eval: bool = False,
    persona_id: str = "excellent",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    **mipro_kwargs
) -> dspy.Module:
    """
    统一入口：从 JSON 加载 trainset（及可选 devset），运行优化器，返回优化后的程序。
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
