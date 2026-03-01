import hashlib
import json
import os
from datetime import datetime
from typing import Callable, Optional

from config import DSPY_OPTIMIZER_CONFIG
from generators.dspy_optimizer import run_optimize_dspy
from api.workspace import WorkspaceManager, get_project_dirs, list_dir_files_with_mtime
from api.routes.llm_config import require_llm_config
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
                        "cards_output_path": cache_data.get("cards_output_path") or "output/optimizer/cards_for_eval.md",
                        "export_path": cache_data.get("export_path") or (req.export_path or "output/optimizer/export_score.json"),
                        "use_auto_eval": True,
                        "hint": "本次未执行 DSPy，使用上次优化结果。",
                        "evaluation_report_path": "output/optimizer/closed_loop_final_report.md",
                        "cache_hit": True,
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

    if req.optimizer_type not in ("bootstrap", "mipro"):
        raise BadRequestError(
            "optimizer_type 须为 bootstrap 或 mipro",
            details={"value": req.optimizer_type},
        )

    kwargs = {
        "trainset_path": trainset_abs,
        "devset_path": devset_abs,
        "output_cards_path": cards_abs,
        "export_path": export_abs,
        "optimizer_type": req.optimizer_type,
        "api_key": llm["api_key"],
        "model_type": model_type,
        "max_rounds": req.max_rounds or cfg.get("max_rounds", 1),
        "max_bootstrapped_demos": cfg.get("max_bootstrapped_demos", 4),
        "persona_id": req.persona_id,
    }
    if progress_callback is not None:
        kwargs["progress_callback"] = progress_callback

    run_optimize_dspy(**kwargs)

    hint = "闭环模式已完成，每轮已自动仿真+评估。"
    final_report_rel = "output/optimizer/closed_loop_final_report.md"

    # 写入缓存，便于下次同一 trainset 直接命中
    if trainset_hash:
        try:
            cache_file = _dspy_cache_path(output_dir, trainset_hash)
            cache_payload = {
                "trainset_path": trainset_path,
                "trainset_hash": trainset_hash,
                "cards_output_path": cards_path,
                "export_path": export_path_rel,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    return {
        "message": "优化完成。优化后的程序已返回（后续可接入保存/加载）。",
        "cards_output_path": cards_path,
        "export_path": export_path_rel,
        "use_auto_eval": True,
        "hint": hint,
        "evaluation_report_path": final_report_rel,
    }

