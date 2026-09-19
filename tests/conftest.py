from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.models import Scene


DEMO_FILE = Path(__file__).resolve().parents[1] / "backend" / "data" / "house2.json"


@pytest.fixture
def demo_scene() -> Scene:
    return Scene.model_validate_json(DEMO_FILE.read_text(encoding="utf-8"))


@pytest.fixture
def client(demo_scene, monkeypatch, tmp_path):
    data_file = tmp_path / "house2.json"
    data_file.write_text(demo_scene.model_dump_json(by_alias=True), encoding="utf-8")
    monkeypatch.setattr(main, "DATA_FILE", data_file)
    monkeypatch.setattr(main, "WORK", {"scene": demo_scene.model_copy(deep=True)})
    monkeypatch.setattr(main, "UNDO", [])
    monkeypatch.setattr(main, "REDO", [])
    monkeypatch.setattr(main, "HISTORY", [])
    with TestClient(main.app) as test_client:
        yield test_client
