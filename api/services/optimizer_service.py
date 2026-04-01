import hashlib
import json
import os
import pickle
from datetime import datetime
from typing import Any, Callable, Optional

from config import DSPY_OPTIMIZER_CONFIG
from generators.trainset_builder import check_trainset_file
from generators.dspy_optimizer import run_optimize_dspy
from api.workspace import WorkspaceManager, get_project_dirs, list_dir_files_with_mtime
from api.exceptions import BadRequestError, ConfigError, NotFoundError

from api.schemas.optimizer import OptimizeRequest

TRAINSET_LIB_SUBDIR = "trainset_lib"


def _default_trainset_path(workspace_id: str) -> Optional[str]:
    """取当前工作区 trainset 库中 mtime 最新的一份，若无则返回 None。"""
    _, output_dir, _ = get_project_dirs(workspace_id)
    lib_dir = os.path.join(output_dir, TRAINSET_LIB_SUBDIR)
    if not os.path.isdir(lib_dir):
        return None
    path_prefix = f"output/{TRAINSET_LIB_SUBDIR}/"
    files = list_dir_files_with_mtime(lib_dir, path_prefix, allowed_ext={".json"})
    if not files:
        return None
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files[0]["path"]


DSPY_CACHE_SUBDIR = "dspy_cache"
RUN_MANIFEST_SUBDIR = "runs"
ARTIFACT_SUBDIR = "artifacts"


def _trainset_content_hash(trainset_abs: str) -> Optional[str]:
    """计算 trainset 文件内容的 SHA256 哈希。"""
    try:
        with open(trainset_abs, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def _dspy_cache_path(output_dir: str, trainset_hash: str) -> str:
    """dspy_cache 目录下以 hash 命名的缓存文件路径。"""
    cache_dir = os.path.join(output_dir, "optimizer", DSPY_CACHE_SUBDIR)
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{trainset_hash}.json")


def _to_output_rel(abs_path: str, output_dir: str) -> str:
    """将 output 目录下绝对路径转为 output/ 开头的相对路径。"""
    rel = os.path.relpath(abs_path, output_dir).replace("\\", "/")
    return f"output/{rel}"


def _save_compiled_artifact(compiled: Any, output_dir: str, run_id: str) -> tuple[Optional[str], str, Optional[str]]:
    """
    尝试保存优化后的 compiled 对象。
    返回: (artifact_rel_path, artifact_format, error_message)
    """
    artifacts_dir = os.path.join(output_dir, "optimizer", ARTIFACT_SUBDIR)
    os.makedirs(artifacts_dir, exist_ok=True)

    # 首选 dspy module 自带 save（通常可读性更好）
    dspy_save_abs = os.path.join(artifacts_dir, f"{run_id}.json")
    if hasattr(compiled, "save"):
        try:
            compiled.save(dspy_save_abs)
            return _to_output_rel(dspy_save_abs, output_dir), "dspy_save_json", None
        except Exception as e:
            save_err = str(e)
        else:
            save_err = None
    else:
        save_err = "compiled 对象不支持 save()"

    # 回退：pickle 兜底
    pickle_abs = os.path.join(artifacts_dir, f"{run_id}.pkl")
    try:
        with open(pickle_abs, "wb") as f:
            pickle.dump(compiled, f)
        return _to_output_rel(pickle_abs, output_dir), "pickle", save_err
    except Exception as e:
        detail = f"{save_err}; pickle失败: {e}" if save_err else f"pickle失败: {e}"
        return None, "none", detail


def _write_run_manifest(output_dir: str, run_id: str, payload: dict[str, Any]) -> str:
    """写入一次优化运行的 manifest，返回相对 output 路径。"""
    runs_dir = os.path.join(output_dir, "optimizer", RUN_MANIFEST_SUBDIR)
    os.makedirs(runs_dir, exist_ok=True)
    abs_path = os.path.join(runs_dir, f"{run_id}.json")
    with open(abs_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return _to_output_rel(abs_path, output_dir)


ProgressCallback = Callable[[int, int, str], None]


def run_optimizer_core(
    req: OptimizeRequest,
    workspace_id: str,
    progress_callback: Optional[ProgressCallback] = None,
) -> dict:
    """核心优化流程：校验、解析路径、调用 DSPy 优化器并返回结果字典。"""
    try:
        from generators import DSPY_AVAILABLE  # type: ignore[attr-defined]
    except Exception:
        DSPY_AVAILABLE = False  # type: ignore[assignment]

    if not DSPY_AVAILABLE:
        raise ConfigError("未安装 dspy-ai，请运行 pip install dspy-ai")

    from api.routes.llm_config import require_llm_config
    llm = require_llm_config(workspace_id)
    wm = WorkspaceManager(workspace_id)
    # 优先使用请求 / 工作区配置中的 model_type，默认退回豆包
    model_type = (req.model_type or llm.get("model_type") or "doubao").lower()
    cfg = DSPY_OPTIMIZER_CONFIG

    trainset_path = req.trainset_path or _default_trainset_path(workspace_id)
    if not trainset_path:
        raise BadRequestError(
            "trainset 库为空，请先上传剧本构建 trainset。",
            details={},
        )
    trainset_abs = wm.resolve_output_path(trainset_path)
    if not os.path.isfile(trainset_abs):
        raise NotFoundError(
            "trainset 文件不存在。请确认路径或先上传剧本构建 trainset。",
            details={"path": trainset_path},
        )
    valid_trainset, trainset_messages = check_trainset_file(
        trainset_abs,
        strict=False,
        check_eval_alignment=True,
    )
    if not valid_trainset:
        raise BadRequestError(
            "trainset 结构校验未通过，请先修复后再运行优化。",
            details={"messages": trainset_messages[:20]},
        )
    trainset_warnings = [m for m in trainset_messages if m.startswith("[建议]")]

    # 缓存：按 trainset 内容 hash 判断是否已跑过，命中则直接返回上次结果
    _, output_dir, _ = get_project_dirs(workspace_id)
    trainset_hash = _trainset_content_hash(trainset_abs)
    if not req.no_cache and trainset_hash:
        cache_file = _dspy_cache_path(output_dir, trainset_hash)
        if os.path.isfile(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                if cache_data.get("trainset_hash") == trainset_hash:
                    return {
                        "message": "命中缓存，未重跑优化。",
                        "trainset_path": trainset_path,
                        "optimizer_type": req.optimizer_type,
                        "cards_output_path": cache_data.get("cards_output_path") or "output/optimizer/cards_for_eval.md",
                        "export_path": cache_data.get("export_path") or (req.export_path or "output/optimizer/export_score.json"),
                        "use_auto_eval": True,
                        "hint": "本次未执行 DSPy，使用上次优化结果。",
                        "evaluation_report_path": "output/optimizer/closed_loop_final_report.md",
                        "cache_hit": True,
                        "run_manifest_path": cache_data.get("run_manifest_path"),
                        "compiled_artifact_path": cache_data.get("compiled_artifact_path"),
                        "compiled_artifact_format": cache_data.get("compiled_artifact_format"),
                        "trainset_warnings": cache_data.get("trainset_warnings", []),
                    }
            except Exception:
                pass

    cards_path = req.cards_output_path or "output/optimizer/cards_for_eval.md"
    # 闭环模式下，export_path 作为评估结果导出文件（JSON），供前端查看与分析
    export_path_rel = req.export_path or "output/optimizer/export_score.json"
    cards_abs = wm.resolve_output_path(cards_path)
    export_abs = wm.resolve_output_path(export_path_rel)

    os.makedirs(os.path.dirname(cards_abs) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(export_abs) or ".", exist_ok=True)

    devset_abs = None
    if req.devset_path:
        devset_abs = wm.resolve_output_path(req.devset_path)
        if not os.path.isfile(devset_abs):
            raise NotFoundError("devset 文件不存在", details={"path": req.devset_path})

    kwargs = {
        "trainset_path": trainset_abs,
        "devset_path": devset_abs,
        "output_cards_path": cards_abs,
        "export_path": export_abs,
        "optimizer_type": req.optimizer_type,
        "api_key": llm["api_key"],
        "model_type": model_type,
        "max_rounds": req.max_rounds or cfg.get("max_rounds", 1),
        "max_bootstrapped_demos": req.max_bootstrapped_demos or cfg.get("max_bootstrapped_demos", 4),
        "use_auto_eval": req.use_auto_eval,
        "persona_id": req.persona_id,
        "persona_ids": req.persona_ids,
    }
    if req.num_candidates is not None:
        kwargs["num_candidates"] = req.num_candidates
    if req.init_temperature is not None:
        kwargs["init_temperature"] = req.init_temperature
    if req.num_threads is not None:
        kwargs["num_threads"] = req.num_threads
    if req.verbose:
        kwargs["verbose"] = True
    if progress_callback is not None:
        kwargs["progress_callback"] = progress_callback

    compiled = run_optimize_dspy(**kwargs)

    hint = "闭环模式已完成，每轮已自动仿真+评估。"
    final_report_rel = "output/optimizer/closed_loop_final_report.md"
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact_rel, artifact_format, artifact_error = _save_compiled_artifact(compiled, output_dir, run_id)
    manifest_payload = {
        "run_id": run_id,
        "workspace_id": workspace_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trainset_path": trainset_path,
        "trainset_hash": trainset_hash,
        "optimizer_type": req.optimizer_type,
        "model_type": model_type,
        "request": {
            "max_rounds": req.max_rounds,
            "max_bootstrapped_demos": req.max_bootstrapped_demos,
            "persona_id": req.persona_id,
            "persona_ids": req.persona_ids,
            "no_cache": req.no_cache,
            "num_candidates": req.num_candidates,
            "init_temperature": req.init_temperature,
            "verbose": req.verbose,
            "num_threads": req.num_threads,
        },
        "outputs": {
            "cards_output_path": cards_path,
            "export_path": export_path_rel,
            "evaluation_report_path": final_report_rel,
            "compiled_artifact_path": artifact_rel,
            "compiled_artifact_format": artifact_format,
            "compiled_artifact_error": artifact_error,
        },
        "trainset_warnings": trainset_warnings[:20],
    }
    manifest_rel = _write_run_manifest(output_dir, run_id, manifest_payload)

    # 写入缓存，便于下次同一 trainset 直接命中
    if trainset_hash:
        try:
            cache_file = _dspy_cache_path(output_dir, trainset_hash)
            cache_payload = {
                "trainset_path": trainset_path,
                "trainset_hash": trainset_hash,
                "cards_output_path": cards_path,
                "export_path": export_path_rel,
                "run_manifest_path": manifest_rel,
                "compiled_artifact_path": artifact_rel,
                "compiled_artifact_format": artifact_format,
                "trainset_warnings": trainset_warnings[:20],
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    return {
        "message": "优化完成。优化后的程序已返回（后续可接入保存/加载）。",
        "trainset_path": trainset_path,
        "optimizer_type": req.optimizer_type,
        "cards_output_path": cards_path,
        "export_path": export_path_rel,
        "use_auto_eval": True,
        "hint": hint,
        "cache_hit": False,
        "evaluation_report_path": final_report_rel,
        "run_manifest_path": manifest_rel,
        "compiled_artifact_path": artifact_rel,
        "compiled_artifact_format": artifact_format,
        "compiled_artifact_error": artifact_error,
        "trainset_warnings": trainset_warnings[:20],
    }

