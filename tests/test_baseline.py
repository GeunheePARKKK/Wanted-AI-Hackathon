import pytest

from backend import main
from backend.detector import inspect_scene
from backend.resolver import apply_action, resolve_violation


# Keys preserve subject roles; generated DE-* IDs change after a fix.
EXPECTED_VIOLATIONS = {
    ("HARD_CLASH", "sofa", "table"): ("HIGH", -250.0, 0.0),
    ("HARD_CLASH", "tv_stand", "wall_b"): ("HIGH", -150.0, 0.0),
    ("ZONE_INTRUSION", "bed", "bedroom_window"): ("MEDIUM", -400.0, 0.0),
    ("ZONE_INTRUSION", "wardrobe", "bedroom_door_swing"): ("MEDIUM", -300.0, 0.0),
    ("USAGE_SPACE", "desk", "bookshelf"): ("MEDIUM", 400.0, 750.0),
    ("OUT_OF_ROOM", "tv_stand", "living"): ("HIGH", -300.0, 0.0),
    ("CIRCULATION", "bedroom_door_swing", "wardrobe"): ("HIGH", 0.0, 600.0),
    ("CIRCULATION", "bed", "wardrobe"): ("HIGH", 0.0, 600.0),
    ("CIRCULATION", "wardrobe", "wardrobe"): ("HIGH", 0.0, 600.0),
}


def violation_key(violation):
    return violation["code"], violation["a"]["id"], violation["b"]["id"]


def assert_demo_baseline(inspection):
    violations = inspection["violations"]
    assert len(violations) == 9
    assert {
        violation_key(v): (v["severity"], v["measured_mm"], v["required_mm"])
        for v in violations
    } == EXPECTED_VIOLATIONS
    assert inspection["summary"]["violations"] == 9
    assert inspection["summary"]["by_severity"] == {"HIGH": 6, "MEDIUM": 3}
    assert inspection["summary"]["score"] == 0


def assert_clean(inspection):
    assert inspection["violations"] == []
    assert inspection["summary"]["violations"] == 0
    assert inspection["summary"]["by_severity"] == {"HIGH": 0, "MEDIUM": 0}
    assert inspection["summary"]["score"] == 100


def test_demo_detects_exact_baseline(demo_scene):
    original = demo_scene.model_dump()
    first = inspect_scene(demo_scene)
    assert_demo_baseline(first)
    assert inspect_scene(demo_scene) == first
    assert demo_scene.model_dump() == original


@pytest.mark.parametrize(
    "target_key", EXPECTED_VIOLATIONS, ids=["-".join(k) for k in EXPECTED_VIOLATIONS]
)
def test_first_candidate_resolves_target_without_new_violations(demo_scene, target_key):
    original = demo_scene.model_dump()
    before = inspect_scene(demo_scene)
    target = next(v for v in before["violations"] if violation_key(v) == target_key)

    resolution = resolve_violation(demo_scene, target["id"])
    assert resolution["violation"] == target
    assert resolution["candidates"]
    first = resolution["candidates"][0]
    assert first["recommended"] is True
    assert first["verified"] is True
    assert first["new_violations"] == 0

    after = inspect_scene(apply_action(demo_scene, first["action"]))
    before_keys = {violation_key(v) for v in before["violations"]}
    after_keys = {violation_key(v) for v in after["violations"]}
    assert target_key not in after_keys
    assert after_keys <= before_keys
    assert first["violations_after"] == after["summary"]["violations"]
    assert demo_scene.model_dump() == original


def test_inspect_api_matches_engine(client, demo_scene):
    response = client.get("/api/inspect")
    assert response.status_code == 200
    assert_demo_baseline(response.json())
    assert response.json() == inspect_scene(demo_scene)


def test_autofix_api_reaches_100_and_supports_undo_redo(client, demo_scene):
    original_file = main.DATA_FILE.read_bytes()
    response = client.post("/api/autofix")
    assert response.status_code == 200
    result = response.json()
    assert result["steps"]
    assert all(step["action"] and step["verified"] for step in result["steps"])
    assert_clean(result["inspection"])

    scene_response = client.get("/api/scene")
    assert scene_response.status_code == 200
    fixed_scene = scene_response.json()
    assert fixed_scene != demo_scene.model_dump(by_alias=True)
    inspection = client.get("/api/inspect")
    assert inspection.status_code == 200
    assert_clean(inspection.json())

    repeated = client.post("/api/autofix")
    assert repeated.status_code == 200
    assert repeated.json()["steps"] == []
    assert_clean(repeated.json()["inspection"])

    undone = client.post("/api/undo")
    assert undone.status_code == 200
    assert_demo_baseline(undone.json())
    restored_scene = client.get("/api/scene")
    assert restored_scene.status_code == 200
    assert restored_scene.json() == demo_scene.model_dump(by_alias=True)

    redone = client.post("/api/redo")
    assert redone.status_code == 200
    assert_clean(redone.json())
    redone_scene = client.get("/api/scene")
    assert redone_scene.status_code == 200
    assert redone_scene.json() == fixed_scene
    assert main.DATA_FILE.read_bytes() == original_file
