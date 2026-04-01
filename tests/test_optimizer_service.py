# -*- coding: utf-8 -*-
"""DSPy 优化服务层测试。"""

from __future__ import annotations

import json
import os
import sys
import types

from api.schemas.optimizer import OptimizeRequest
from api.services import optimizer_service as svc


class _DummyWorkspaceManager:
    def __init__(self, output_dir: str):
        self._output_dir = output_dir

    def resolve_output_path(self, relative_path: str, must_exist: bool = False) -> str:
        rel = (relative_path or "").replace("\\", "/").lstrip("/")
        if rel.startswith("output/"):
            rel = rel[len("output/") :]
        abs_path = os.path.join(self._output_dir, rel)
        if must_exist and not os.path.exists(abs_path):
            raise FileNotFoundError(abs_path)
        return abs_path


class _DummyCompiled:
    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ok": True}, f)


def _install_common_mocks(monkeypatch, tmp_path):
    workspace_root = tmp_path / "ws"
    input_dir = workspace_root / "input"
    output_dir = workspace_root / "output"
    lib_dir = output_dir / "trainset_lib"
    input_dir.mkdir(parents=True)
    lib_dir.mkdir(parents=True)

    trainset_path = lib_dir / "demo_trainset.json"
    trainset_path.write_text(
        json.dumps(
            [
                {
                    "full_script": "任务目标：完成装配。评分标准：满分100。",
                    "stages": [
                        {
                            "id": 1,
                            "title": "阶段一",
                            "description": "desc",
                            "role": "教师",
                            "task": "任务",
                            "key_points": ["要点1"],
                            "content_excerpt": "摘录",
                        }
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        svc,
        "get_project_dirs",
        lambda workspace_id: (str(input_dir), str(output_dir), str(workspace_root)),
    )
    monkeypatch.setattr(
        svc,
        "list_dir_files_with_mtime",
        lambda lib_dir_abs, path_prefix, allowed_ext: [
            {"path": "output/trainset_lib/demo_trainset.json", "mtime": 999999}
        ],
    )
    fake_llm_cfg = types.ModuleType("api.routes.llm_config")
    fake_llm_cfg.require_llm_config = lambda workspace_id: {
        "api_key": "test-key",
        "model_type": "doubao",
    }
    monkeypatch.setitem(sys.modules, "api.routes.llm_config", fake_llm_cfg)
    monkeypatch.setattr(
        svc,
        "WorkspaceManager",
        lambda workspace_id: _DummyWorkspaceManager(str(output_dir)),
    )
    monkeypatch.setattr(
        svc,
        "check_trainset_file",
        lambda *args, **kwargs: (True, ["[建议] 可补充更多高质量样本"]),
    )
    monkeypatch.setattr(svc, "run_optimize_dspy", lambda **kwargs: _DummyCompiled())

    fake_generators = types.ModuleType("generators")
    fake_generators.DSPY_AVAILABLE = True
    monkeypatch.setitem(sys.modules, "generators", fake_generators)
    return output_dir


def test_run_optimizer_core_writes_manifest_and_artifact(monkeypatch, tmp_path):
    """无 trainset_path 时应自动选最新 trainset，并生成 manifest/artifact。"""
    output_dir = _install_common_mocks(monkeypatch, tmp_path)

    req = OptimizeRequest(
        trainset_path=None,
        optimizer_type="bootstrap",
        no_cache=True,
    )
    result = svc.run_optimizer_core(req, workspace_id="w-test")

    assert result["cache_hit"] is False
    assert result["trainset_path"] == "output/trainset_lib/demo_trainset.json"
    assert result["run_manifest_path"].startswith("output/optimizer/runs/")
    assert result["compiled_artifact_path"].startswith("output/optimizer/artifacts/")
    assert result["compiled_artifact_format"] in {"dspy_save_json", "pickle"}
    assert "[建议]" in result["trainset_warnings"][0]

    manifest_abs = output_dir / result["run_manifest_path"].replace("output/", "", 1)
    assert manifest_abs.exists()


def test_run_optimizer_core_cache_hit_returns_cached_artifacts(monkeypatch, tmp_path):
    """命中缓存时应直接返回历史 manifest/artifact 信息。"""
    output_dir = _install_common_mocks(monkeypatch, tmp_path)
    trainset_abs = output_dir / "trainset_lib" / "demo_trainset.json"
    trainset_hash = svc._trainset_content_hash(str(trainset_abs))
    cache_file = output_dir / "optimizer" / "dspy_cache" / f"{trainset_hash}.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "trainset_hash": trainset_hash,
                "cards_output_path": "output/optimizer/cards_for_eval.md",
                "export_path": "output/optimizer/export_score.json",
                "run_manifest_path": "output/optimizer/runs/20260101_000000.json",
                "compiled_artifact_path": "output/optimizer/artifacts/20260101_000000.json",
                "compiled_artifact_format": "dspy_save_json",
                "trainset_warnings": ["[建议] 样本可扩充"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    req = OptimizeRequest(trainset_path=None, optimizer_type="bootstrap", no_cache=False)
    result = svc.run_optimizer_core(req, workspace_id="w-test")

    assert result["cache_hit"] is True
    assert result["run_manifest_path"] == "output/optimizer/runs/20260101_000000.json"
    assert result["compiled_artifact_path"] == "output/optimizer/artifacts/20260101_000000.json"
    assert result["trainset_warnings"] == ["[建议] 样本可扩充"]
