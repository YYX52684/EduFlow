# -*- coding: utf-8 -*-
"""CLI 模拟与评估：学生模拟测试、批量模拟、仅评估。"""
import os
import sys


def run_simulation(
    md_path: str,
    persona_id: str = "excellent",
    mode: str = "auto",
    output_dir: str = "simulator_output",
    verbose: bool = False,
    run_evaluation: bool = True,
):
    """运行学生模拟测试，可选运行评估。"""
    from simulator import SessionRunner, SessionConfig, SessionMode
    from simulator import Evaluator, EvaluatorFactory

    print("=" * 60)
    print("学生模拟测试")
    print("=" * 60)
    print(f"\n卡片文件: {md_path}")
    print(f"人设: {persona_id}")
    print(f"模式: {mode}\n")
    config = SessionConfig(
        mode=SessionMode(mode),
        persona_id=persona_id,
        output_dir=output_dir,
        verbose=verbose,
    )
    runner = SessionRunner(config)
    runner.load_cards(md_path)
    runner.setup()
    try:
        log = runner.run()
        if run_evaluation and log.summary.get("status") == "completed":
            print("\n" + "=" * 60)
            print("开始评估对话质量...")
            print("=" * 60)
            evaluator = EvaluatorFactory.create_from_env()
            dialogue = runner.get_dialogue_for_evaluation()
            report = evaluator.evaluate(dialogue, session_id=log.session_id)
            reports_dir = os.path.join(output_dir, "reports")
            evaluator.save_report(report, reports_dir)
            print("\n[完成] 模拟测试和评估已完成!")
        else:
            print("\n[完成] 模拟测试已完成（跳过评估）")
    except KeyboardInterrupt:
        print("\n[中断] 用户中断测试")
    except Exception as e:
        print(f"\n[错误] 模拟测试失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def run_batch_simulation(
    md_path: str,
    personas: list,
    output_dir: str = "simulator_output",
    verbose: bool = False,
):
    """批量运行多个人设的模拟测试。"""
    print("=" * 60)
    print("批量学生模拟测试")
    print("=" * 60)
    print(f"\n卡片文件: {md_path}")
    print(f"人设列表: {', '.join(personas)}\n")
    results = []
    for i, persona in enumerate(personas, 1):
        print(f"\n{'='*40}")
        print(f"[{i}/{len(personas)}] 测试人设: {persona}")
        print(f"{'='*40}")
        persona_output = os.path.join(output_dir, f"persona_{persona}")
        try:
            run_simulation(
                md_path=md_path,
                persona_id=persona,
                mode="auto",
                output_dir=persona_output,
                verbose=verbose,
                run_evaluation=True,
            )
            results.append((persona, "成功"))
        except Exception as e:
            print(f"[错误] 人设 {persona} 测试失败: {e}")
            results.append((persona, f"失败: {e}"))
    print("\n" + "=" * 60)
    print("批量测试结果汇总")
    print("=" * 60)
    for persona, status in results:
        print(f"  - {persona}: {status}")


def run_evaluation_only(log_path: str, output_dir: str = None):
    """仅运行评估（对已有对话日志）。"""
    from simulator import evaluate_session

    print("=" * 60)
    print("对话质量评估")
    print("=" * 60)
    print(f"\n日志文件: {log_path}")
    if not os.path.exists(log_path):
        print(f"[错误] 日志文件不存在: {log_path}")
        sys.exit(1)
    try:
        report = evaluate_session(log_path, output_dir)
        print(f"\n[完成] 评估完成!")
        print(f"  总分: {report.total_score:.1f}/100")
        print(f"  评级: {report.get_rating()}")
    except Exception as e:
        print(f"\n[错误] 评估失败: {e}")
        sys.exit(1)


def run_simulate_platform(args, parser):
    """使用平台侧 LLM 进行学生模拟测试（学生本地 LLM，老师在智慧树平台）。"""
    from simulator.platform_client import PlatformTrainConfig, PlatformTrainClient
    from simulator.student_persona import PersonaManager
    from simulator.llm_student import StudentFactory
    from config import PLATFORM_CONFIG

    step_id = (args.platform_step_id or "").strip()
    if not step_id:
        step_id = PLATFORM_CONFIG.get("start_node_id", "").strip()
    if not step_id:
        parser.error("--simulate-platform 需要提供 --platform-step-id，或在平台配置中设置 PLATFORM_START_NODE_ID")

    print("=" * 60)
    print("学生模拟测试（平台LLM模式）")
    print("=" * 60)
    print(f"\n训练任务ID: {PLATFORM_CONFIG.get('train_task_id', '')}")
    print(f"起始节点 stepId: {step_id}")
    print(f"人设: {args.persona}")
    print()

    pt_cfg = PlatformTrainConfig.from_env()
    client = PlatformTrainClient(pt_cfg)
    manager = PersonaManager()
    persona = manager.get_persona(args.persona)
    student = StudentFactory.create_from_env(persona)

    try:
        first = client.run_card(step_id=step_id)
    except Exception as e:
        print(f"[错误] 调用平台 runCard 失败: {e}")
        sys.exit(1)

    data = first.get("data") or {}
    npc_text = data.get("text") or ""
    print("[平台 NPC 开场白]:", npc_text or "(无文本返回)")
    print("sessionId:", client.session_id or "(空)")
    if not npc_text:
        print("[提示] 平台未返回开场白文本，结束。")
        return

    max_rounds = 10
    for i in range(max_rounds):
        student_reply = student.generate_response(npc_text)
        print(f"\n[学生 第{i+1}轮]: {student_reply}")
        try:
            resp = client.chat(step_id=step_id, text=student_reply)
        except Exception as e:
            print(f"[错误] 调用平台 chat 失败: {e}")
            break
        npc_text = PlatformTrainClient.extract_npc_reply(resp)
        print(f"[平台 NPC 第{i+1}轮]: {npc_text}")
        data = resp.get("data") or {}
        if data.get("needSkipStep"):
            print("\n[提示] 平台返回 needSkipStep=True，可能需要跳转到 nextStepId =", data.get("nextStepId"))
            break
        if not (data.get("text") or "").strip():
            print("\n[提示] 平台未返回新的 NPC 文本，结束。")
            break
