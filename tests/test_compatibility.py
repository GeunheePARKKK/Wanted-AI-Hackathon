import json
from pathlib import Path

import pytest

from backend.detector import inspect_scene
from backend.geometry import boxes_overlap
from backend.models import Box, Equipment, Furniture, Pipe, Scene, Walkway


def test_old_and_new_model_names_and_json_keys(demo_scene):
    assert Equipment is Furniture
    assert Pipe is Walkway
    assert demo_scene.furniture is demo_scene.equipment
    assert demo_scene.walkways is demo_scene.pipes
    canonical = demo_scene.model_dump()
    legacy = demo_scene.model_dump(by_alias=True)
    assert "furniture" in canonical and "equipment" not in canonical
    assert "equipment" in legacy and "furniture" not in legacy
    assert "pipes" in legacy and "walkways" in canonical
    assert Scene.model_validate(canonical) == Scene.model_validate(legacy)
    replacement = list(demo_scene.furniture)
    demo_scene.equipment = replacement
    assert demo_scene.furniture is replacement


@pytest.mark.parametrize("name", ["house2.json", "house.json", "studio.json"])
def test_legacy_demo_files_still_load(name):
    path = Path(__file__).resolve().parents[1] / "backend" / "data" / name
    scene = Scene.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert scene.furniture
    inspect_scene(scene)


@pytest.mark.parametrize("offset,overlap", [(1.0, False), (1.1, False), (0.999999, True)])
def test_zero_depth_contact_is_not_a_clash(offset, overlap):
    assert boxes_overlap((0, 0, 0), (1, 1, 1), (offset, 0, 0), (offset+1, 1, 1)) is overlap
    scene = Scene.model_validate({
        "meta": {"name": "Test", "room": {"min": [0, 0, 0], "max": [4, 4, 3]}},
        "rules": {}, "structures": [],
        "equipment": [
            {"id": "a", "name": "A", "type": "table", "box": {"min": [0, 0, 0], "max": [1, 1, 1]}},
            {"id": "b", "name": "B", "type": "table",
             "box": {"min": [offset, 0, 0], "max": [offset+1, 1, 1]}},
        ],
    })
    violations = inspect_scene(scene)["violations"]
    assert bool([v for v in violations if v["code"] == "HARD_CLASH"]) is overlap
    assert all(v["a"]["kind"] == "furniture" for v in violations)


def test_duplicate_ids_and_invalid_boxes_are_rejected(demo_scene):
    raw = demo_scene.model_dump()
    raw["furniture"][0]["id"] = raw["furniture"][1]["id"]
    with pytest.raises(ValueError, match="unique"):
        Scene.model_validate(raw)
    with pytest.raises(ValueError, match="finite"):
        Box(min=[float("nan"), 0, 0], max=[1, 1, 1])
