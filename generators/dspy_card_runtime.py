"""
DSPy 卡片生成运行时支持。

集中管理 dspy.configure 的串行化、专用执行线程与优化器上下文。
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import dspy

# dspy.configure 为全局状态，并发时需串行化 LM 配置与调用。
_dspy_lm_lock = threading.Lock()

# dspy.settings 为线程局部，只能由最初配置的线程修改。
_dspy_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dspy-card-gen")

# DSPy 优化器在非主线程运行时，需在当前线程内直接执行生成。
_optimizer_context = threading.local()


def invoke_with_lm(lm: dspy.LM, module: Callable[..., Any], **kwargs: Any) -> Any:
    """统一串行化 dspy.configure 与模块调用。"""
    with _dspy_lm_lock:
        dspy.configure(lm=lm)
        return module(**kwargs)


def run_in_generation_context(task: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """按当前线程上下文选择直接执行或切到专用生成线程。"""
    in_optimizer = getattr(_optimizer_context, "running", False)
    if threading.current_thread() is threading.main_thread() or in_optimizer:
        return task(*args, **kwargs)

    future = _dspy_executor.submit(task, *args, **kwargs)
    return future.result()
