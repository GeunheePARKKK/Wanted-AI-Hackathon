import pytest

from backend import commands, main
from backend.detector import inspect_scene
from backend.models import Scene
from backend.resolver import _vkey


BAD = {"ops": [{"op": "move", "id": "sofa", "delta": [-3, 0, 0]}], "reply": "Moved"}


def test_reject_retry_then_force_same_ops_without_llm(client, monkeypatch):
    calls = []
    def proposal(prompt):
        calls.append(prompt)
        return BAD
    monkeypatch.setattr(commands, "_call_claude", proposal)
    before = client.get("/api/scene").json()
    response = client.post("/api/command?lang=en", json={"text": "Move"})
    result = response.json()
    assert result["blocked"] is True
    assert len(result["new_violations"]) > 0
    assert result["applied"] == []
    assert "new violations" in result["reply"]
    assert len(calls) == 2
    assert "Engine rejected" in calls[1]
    assert client.get("/api/scene").json() == before
    assert main.UNDO == []
    applied = client.post("/api/command/apply", json={"token": result["token"]})
    assert applied.status_code == 200
    assert applied.json()["ops"] == BAD["ops"]
    assert len(calls) == 2
    sofa = next(e for e in client.get("/api/scene").json()["equipment"] if e["id"] == "sofa")
    assert sofa["box"]["min"][0] == pytest.approx(-1.8)
    assert client.post("/api/command/apply", json={"token": result["token"]}).status_code == 409
    client.post("/api/undo")
    assert client.get("/api/scene").json() == before


def test_retry_can_return_safe_plan(client, monkeypatch):
    replies = iter([BAD, {"ops": [{"op": "delete", "id": "table"}], "reply": "Removed table"}])
    monkeypatch.setattr(commands, "_call_claude", lambda prompt: next(replies))
    result = client.post("/api/command", json={"text": "Fix table"}).json()
    assert result["applied"]
    assert not result.get("blocked")
    assert "table" not in [e["id"] for e in client.get("/api/scene").json()["equipment"]]


def test_stale_pending_command_is_rejected(client, monkeypatch):
    monkeypatch.setattr(commands, "_call_claude", lambda prompt: BAD)
    result = client.post("/api/command", json={"text": "Move"}).json()
    client.post("/api/reset")
    assert client.post("/api/command/apply", json={"token": result["token"]}).status_code == 409


def test_command_is_atomic_on_invalid_op(client, monkeypatch):
    monkeypatch.setattr(commands, "_call_claude", lambda prompt: {
        "ops": [{"op": "delete", "id": "table"}, {"op": "move", "id": "missing", "delta": [1, 0, 0]}]})
    before = client.get("/api/scene").json()
    result = client.post("/api/command", json={"text": "Change layout"}).json()
    assert result["error"]
    assert result["applied"] == []
    assert client.get("/api/scene").json() == before
    assert main.UNDO == []


def test_concurrent_edit_rejects_llm_result(client, monkeypatch):
    def proposal(prompt):
        main._mutate(main.WORK["scene"].model_copy(deep=True))
        return {"ops": [{"op": "delete", "id": "table"}]}
    monkeypatch.setattr(commands, "_call_claude", proposal)
    assert client.post("/api/command", json={"text": "Delete table"}).status_code == 409
    assert any(e.id == "table" for e in main.WORK["scene"].equipment)


def test_place_deterministically_finds_safe_room_position():
    scene = Scene.model_validate({
        "meta": {"name": "Test", "room": {"min": [0, 0, 0], "max": [4, 4, 3]}},
        "rules": {}, "structures": [], "equipment": [],
        "rooms": [{"id": "study", "name": "서재", "box": {"min": [0, 0, 0], "max": [4, 4, 3]}}],
    })
    op = {"op": "place", "type": "desk", "room": "study"}
    twin = scene.model_copy(deep=True)
    commands._apply_op(scene, op)
    commands._apply_op(twin, op)
    assert scene == twin
    assert inspect_scene(scene)["violations"] == []
    desk = scene.equipment[0]
    cx = sum([desk.box.min[0], desk.box.max[0]]) / 2
    assert cx * 10 == pytest.approx(round(cx * 10))
    assert desk.rotation in (0, 90, 180, 270)


def test_place_existing_furniture_does_not_add_violations(demo_scene):
    before = {_vkey(v) for v in inspect_scene(demo_scene)["violations"]}
    commands._apply_op(demo_scene, {"op": "place", "id": "desk", "room": "study", "near": "bookshelf"})
    after = {_vkey(v) for v in inspect_scene(demo_scene)["violations"]}
    assert after <= before
    assert len([e for e in demo_scene.equipment if e.id == "desk"]) == 1


def test_impossible_place_and_unknown_near_are_explicit(demo_scene):
    original = demo_scene.model_dump(by_alias=True)
    with pytest.raises(ValueError, match="near|대상"):
        commands._apply_op(demo_scene, {"op": "place", "id": "bed", "room": "study", "near": "missing"})
    demo_scene.rooms[2].box.max = [5.3, 0.2, 2.4]
    with pytest.raises(ValueError, match="위치|placement"):
        commands._apply_op(demo_scene, {"op": "place", "id": "bed", "room": "study"})
    assert demo_scene.equipment[5].model_dump() == original["equipment"][5]
