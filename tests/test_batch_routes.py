# -*- coding: utf-8 -*-
"""批量解析与批量卡片生成接口测试。"""

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import app
from api.routes import auth as auth_routes
from api.routes import cards as cards_route
from api.routes import script as script_route


def _override_workspace() -> str:
    return "test-workspace"


def _mock_stage(title: str) -> dict:
    return {
        "id": 1,
        "title": title,
        "description": f"描述-{title}",
        "role": "教师",
        "task": f"任务-{title}",
        "key_points": ["要点1"],
        "content_excerpt": f"摘录-{title}",
        "interaction_rounds": 2,
    }


def test_script_upload_batch_returns_per_file_results(monkeypatch, tmp_path):
    """upload-batch 应返回逐文件结果，并保留输入顺序。"""
    output_dir = tmp_path / "output"
    input_dir = tmp_path / "input"
    output_dir.mkdir()
    input_dir.mkdir()

    class DummySplitter:
        def __init__(self, *args, **kwargs):
            pass

        def analyze(self, full_content: str):
            return {"stages": [_mock_stage(full_content.strip())]}

    monkeypatch.setattr(
        script_route,
        "get_project_dirs",
        lambda workspace_id: (str(input_dir), str(output_dir), str(tmp_path)),
    )
    monkeypatch.setattr(script_route, "ContentSplitter", DummySplitter)
    monkeypatch.setattr(script_route, "_parse_file_to_content", lambda path, suffix: Path(path).read_text(encoding="utf-8"))

    app.dependency_overrides[auth_routes.require_workspace_owned] = _override_workspace
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/script/upload-batch",
            files=[
                ("files", ("任务一.md", "第一份材料", "text/markdown")),
                ("files", ("任务二.md", "第二份材料", "text/markdown")),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_count"] == 2
    assert data["success_count"] == 2
    assert data["failure_count"] == 0
    assert [item["filename"] for item in data["results"]] == ["任务一.md", "任务二.md"]
    assert all(item["success"] is True for item in data["results"])
    assert all(item["stages_count"] == 1 for item in data["results"])


def test_cards_generate_batch_uses_unique_cards_filename(monkeypatch, tmp_path):
    """generate-batch 在同名源文件并发生成时应自动追加序号避免覆盖。"""
    workspace_root = tmp_path / "workspace"
    input_dir = workspace_root / "input"
    output_dir = workspace_root / "output"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    class DummyGenerator:
        def __init__(self, *args, **kwargs):
            pass

        def generate_all_cards(self, stages, full_content, **kwargs):
            return f"# 卡片\n\n{full_content}\n\n{stages[0]['title']}"

    monkeypatch.setattr(
        cards_route,
        "get_project_dirs",
        lambda workspace_id: (str(input_dir), str(output_dir), str(workspace_root)),
    )
    monkeypatch.setattr(
        cards_route,
        "get_workspace_dirs",
        lambda workspace_id: (str(input_dir), str(output_dir), str(workspace_root)),
    )
    monkeypatch.setattr(
        cards_route,
        "require_llm_config",
        lambda workspace_id: {
            "api_key": "test-key",
            "model_type": "doubao",
            "base_url": "https://example.com",
            "model": "test-model",
        },
    )
    monkeypatch.setattr(cards_route, "list_frameworks", lambda: [{"id": "dspy", "name": "DSPy"}])
    monkeypatch.setattr(cards_route, "get_framework", lambda framework_id: (DummyGenerator, {"id": framework_id}))
    monkeypatch.setattr(cards_route, "build_evaluation_markdown", lambda *args, **kwargs: "")

    app.dependency_overrides[auth_routes.require_workspace_owned] = _override_workspace
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/cards/generate-batch",
            json={
                "items": [
                    {
                        "full_content": "第一份内容",
                        "stages": [_mock_stage("同名-A")],
                        "framework_id": "dspy",
                        "source_filename": "同名.md",
                    },
                    {
                        "full_content": "第二份内容",
                        "stages": [_mock_stage("同名-B")],
                        "framework_id": "dspy",
                        "source_filename": "同名.docx",
                    },
                ],
                "max_concurrency": 2,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success_count"] == 2
    assert data["failure_count"] == 0
    output_paths = [item["output_path"] for item in data["results"]]
    assert output_paths == ["output/cards_同名.md", "output/cards_同名_2.md"]
    assert (output_dir / "cards_同名.md").exists()
    assert (output_dir / "cards_同名_2.md").exists()
