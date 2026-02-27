"""
闭环优化：生成 → 仿真 → 评估 → 反哺优化器

将内部仿真与评估作为 DSPy 优化器的自动 metric，替代外部平台人工评估，
实现「生成 → 仿真 → 评估」闭环，使卡片质量随迭代提升。
支持三档人设（优秀/一般/较差）并行仿真，取均值作为评估得分。
"""

import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List, Tuple


def _build_llm_config(api_key: str, model_type: str) -> Tuple[dict, dict]:
    """根据 model_type 构建仿真器与评估器的 LLM 配置。"""
    from config import DEFAULT_MODEL_TYPE
    model_type = (model_type or DEFAULT_MODEL_TYPE).lower()
    if model_type == "doubao":
        from config import DOUBAO_BASE_URL, DOUBAO_MODEL, DOUBAO_SERVICE_CODE
        base_url = (DOUBAO_BASE_URL or "").rstrip("/")
        api_url = f"{base_url}/chat/completions" if base_url else ""
        one = {
            "api_url": api_url,
            "api_key": api_key,
            "model": DOUBAO_MODEL or "Doubao-1.5-pro-32k",
            "service_code": DOUBAO_SERVICE_CODE or "",
        }
    else:
        from config import DEEPSEEK_CHAT_URL, DEEPSEEK_MODEL
        one = {
            "api_url": DEEPSEEK_CHAT_URL or "https://api.deepseek.com/v1/chat/completions",
            "api_key": api_key,
            "model": DEEPSEEK_MODEL or "deepseek-chat",
        }
    return one, one


def run_simulate_and_evaluate(
    cards_path: str,
    output_dir: str,
    api_key: str,
    model_type: str = "doubao",
    persona_id: str = "excellent",
    max_rounds_per_card: Optional[int] = None,
    total_max_rounds: Optional[int] = None,
    save_logs: bool = True,
    verbose: bool = False,
    api_url: Optional[str] = None,
    model_name: Optional[str] = None,
    progress_callback: Optional[Callable[[str, str], None]] = None,
) -> Tuple[Any, Any]:
    """
    运行仿真并评估，返回 (SessionLog, EvaluationReport)。

    Args:
        cards_path: 卡片 Markdown 文件路径
        output_dir: 仿真输出目录
        api_key: LLM API 密钥
        model_type: "doubao" | "deepseek"
        persona_id: 学生人设
        max_rounds_per_card: 单卡片最大轮次
        total_max_rounds: 总会话最大轮次
        save_logs: 是否保存会话日志
        verbose: 详细输出
        progress_callback: 可选，phase 变化时调用 (phase, message)，用于流式 UI

    Returns:
        (session_log, evaluation_report)
    """
    from simulator.session_runner import SessionRunner, SessionConfig, SessionMode
    from simulator.evaluator import Evaluator

    def progress(phase: str, message: str) -> None:
        if progress_callback:
            progress_callback(phase, message)

    sim_config, eval_config = _build_llm_config(api_key, model_type)
    if api_url:
        sim_config["api_url"] = api_url
        eval_config["api_url"] = api_url
    if model_name:
        sim_config["model"] = model_name
        eval_config["model"] = model_name
    if not sim_config.get("api_url") or not sim_config.get("api_key"):
        raise ValueError("未配置 LLM API，请检查 api_key 与 model_type")

    from config import DSPY_OPTIMIZER_CONFIG
    _cfg = DSPY_OPTIMIZER_CONFIG
    if max_rounds_per_card is None:
        max_rounds_per_card = _cfg.get("closed_loop_max_rounds_per_card", 5)
    if total_max_rounds is None:
        total_max_rounds = _cfg.get("closed_loop_total_max_rounds", 50)

    progress("loading", "加载卡片…")
    config = SessionConfig(
        mode=SessionMode.AUTO,
        persona_id=persona_id,
        output_dir=output_dir,
        verbose=verbose,
        save_logs=save_logs,
        npc_config=sim_config,
        student_config=sim_config,
        max_rounds_per_card=max_rounds_per_card,
        total_max_rounds=total_max_rounds,
        progress_callback=progress_callback,
    )
    runner = SessionRunner(config)
    runner.load_cards(cards_path)
    runner.setup()

    progress("simulate", "仿真中（学生与 NPC 对话，可能较久）…")
    log = runner.run()

    # 仅当会话正常完成时才评估
    status = (log.summary or {}).get("status", "")
    if status != "completed":
        # 未完成时返回一个低分报告，避免优化器误用
        from simulator.evaluator import EvaluationReport, DimensionScore
        dummy_report = EvaluationReport(
            session_id=log.session_id,
            evaluation_time="",
            total_score=0.0,
            dimensions=[],
            summary=f"会话未完成 (status={status})",
            recommendations=["请检查卡片逻辑或轮次限制"],
        )
        return log, dummy_report

    progress("evaluate", "评估对话质量…")
    dialogue = runner.get_dialogue_for_evaluation()
    evaluator = Evaluator(eval_config)
    report = evaluator.evaluate(dialogue, session_id=log.session_id)
    return log, report


def make_auto_metric(
    output_cards_path: str,
    export_path: str,
    export_config: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    model_type: str = "doubao",
    persona_id: str = "excellent",
    persona_ids: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    prompt_user: bool = False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    total_estimate: int = 1,
) -> Callable:
    """
    返回 DSPy 所需的 metric(example, pred, trace=None) -> score。

    行为：将 pred.cards 写入 output_cards_path，运行仿真 + 评估，
    将报告写入 export_path，并返回 total_score。
    若 persona_ids 为多个人设，则并行运行三档（优秀/一般/较差）仿真，取均值作为最终得分。

    Args:
        output_cards_path: 生成卡片写入路径
        export_path: 评估报告导出路径（JSON，含 total_score）
        export_config: 预留参数（当前闭环模式下未使用，可传 None）
        api_key: LLM API 密钥（不传则从 config 取）
        model_type: "doubao" | "deepseek"
        persona_id: 单一人设（persona_ids 为空时使用，兼容旧逻辑）
        persona_ids: 多个人设 ID，如 ["excellent","average","struggling"]，并行运行取均值
        output_dir: 仿真输出目录（默认在 optimizer 下创建 closed_loop_sim）
        prompt_user: 是否打印提示（闭环模式下通常为 False）
    """
    from config import DOUBAO_API_KEY, DEEPSEEK_API_KEY, DEFAULT_MODEL_TYPE
    model_type = model_type or DEFAULT_MODEL_TYPE
    if api_key is None:
        api_key = DOUBAO_API_KEY if model_type == "doubao" else DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError("未配置 API Key，请设置 DEEPSEEK_API_KEY 或 LLM_API_KEY（豆包）")

    base_dir = os.path.dirname(os.path.abspath(output_cards_path))
    sim_output = output_dir or os.path.join(base_dir, "closed_loop_sim")
    os.makedirs(sim_output, exist_ok=True)
    _progress_count = [0]  # mutable for closure

    # 三档人设并行时使用，否则单一人设
    ids_to_run = persona_ids if persona_ids and len(persona_ids) > 1 else [persona_id]

    def _run_one(persona: str, cards_path: str, out_subdir: str) -> Tuple[Optional[float], Optional[Any], Optional[Any]]:
        """单个人设的仿真+评估，返回 (score, log, report)。"""
        try:
            log, report = run_simulate_and_evaluate(
                cards_path=cards_path,
                output_dir=out_subdir,
                api_key=api_key,
                model_type=model_type,
                persona_id=persona,
                save_logs=True,
                verbose=False,
            )
            return float(report.total_score), log, report
        except Exception as e:
            if prompt_user:
                print(f"  [metric] 人设 {persona} 仿真/评估失败: {e}")
            return 0.0, None, None

    def metric(example, pred, trace=None):
        cards = getattr(pred, "cards", None)
        if cards is None:
            return 0.0
        path = os.path.abspath(output_cards_path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(cards)

        n = _progress_count[0] + 1
        _progress_count[0] = n

        def sim_progress(phase: str, message: str) -> None:
            if progress_callback:
                progress_callback(n, total_estimate, message)

        if progress_callback:
            progress_callback(n, total_estimate, f"第 {n} 次评估：仿真+评估中…")
        if prompt_user:
            print(f"\n  [metric] 已写入卡片到: {path}")
            print(f"  [metric] 运行闭环（{len(ids_to_run)} 档人设）...")

        scores: List[float] = []
        reports: List[Any] = []
        logs: List[Any] = []

        if len(ids_to_run) > 1:
            # 三档人设并行，取均值
            with ThreadPoolExecutor(max_workers=len(ids_to_run)) as ex:
                futures = {
                    ex.submit(
                        _run_one,
                        persona,
                        path,
                        os.path.join(sim_output, f"persona_{persona}"),
                    ): persona
                    for persona in ids_to_run
                }
                for fut in as_completed(futures):
                    sc, lg, rpt = fut.result()
                    scores.append(sc)
                    if rpt:
                        reports.append(rpt)
                    if lg:
                        logs.append(lg)
            mean_score = sum(scores) / len(scores) if scores else 0.0
            report = reports[0] if reports else None
            log = logs[0] if logs else None
        else:
            try:
                log, report = run_simulate_and_evaluate(
                    cards_path=path,
                    output_dir=sim_output,
                    api_key=api_key,
                    model_type=model_type,
                    persona_id=ids_to_run[0],
                    save_logs=True,
                    verbose=False,
                    progress_callback=sim_progress,
                )
                mean_score = float(report.total_score)
            except Exception as e:
                if prompt_user:
                    print(f"  [metric] 仿真/评估失败: {e}")
                os.makedirs(os.path.dirname(os.path.abspath(export_path)) or ".", exist_ok=True)
                with open(export_path, "w", encoding="utf-8") as f:
                    json.dump({"total_score": 0.0, "error": str(e)}, f, ensure_ascii=False, indent=2)
                return 0.0

        export_dir = os.path.dirname(os.path.abspath(export_path))
        os.makedirs(export_dir or ".", exist_ok=True)
        export_data = report.to_dict() if report is not None else {"total_score": mean_score}
        if len(scores) > 1:
            export_data["persona_scores"] = dict(zip(ids_to_run, scores))
            export_data["mean_score"] = mean_score
            export_data["total_score"] = mean_score
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        if report is not None and log is not None:
            logs_dir = os.path.join(sim_output, "logs")
            log_md_rel = os.path.join(os.path.basename(sim_output), "logs", f"session_{log.session_id}.md")
            log_json_rel = os.path.join(os.path.basename(sim_output), "logs", f"session_{log.session_id}.json")
            final_report_path = os.path.join(export_dir, "closed_loop_final_report.md")
            with open(final_report_path, "w", encoding="utf-8") as f:
                f.write(report.to_markdown())
                if len(scores) > 1:
                    f.write(f"\n\n---\n\n## 三档人设得分\n\n")
                    for pid, sc in zip(ids_to_run, scores):
                        f.write(f"- {pid}: {sc}\n")
                    f.write(f"- **均值**: {mean_score}\n\n")
                f.write("\n---\n\n## 本次模拟会话日志\n\n")
                f.write(f"- **会话ID**: {log.session_id}\n")
                f.write(f"- **日志(Markdown)**: `{log_md_rel}`\n")
                f.write(f"- **日志(JSON)**: `{log_json_rel}`\n")
                log_md_abs = os.path.join(logs_dir, f"session_{log.session_id}.md")
                if os.path.isfile(log_md_abs):
                    f.write("\n### 会话日志摘要\n\n```\n")
                    with open(log_md_abs, "r", encoding="utf-8") as lf:
                        f.write(lf.read()[:8000].replace("```", "` ` `"))
                    if os.path.getsize(log_md_abs) > 8000:
                        f.write("\n... (已截断)\n")
                    f.write("\n```\n")

        if prompt_user:
            print(f"  [metric] 评估完成，总分: {mean_score}，已写入: {export_path}")

        return float(mean_score)

    return metric
