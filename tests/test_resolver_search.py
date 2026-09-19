from time import perf_counter

from backend.detector import inspect_scene
from backend.models import Scene
from backend.resolver import Resolver, _vkey, apply_action, resolve_violation


def test_structure_targets_never_generate_moving_candidates(demo_scene):
    violations = inspect_scene(demo_scene)["violations"]
    furniture_ids = {e.id for e in demo_scene.equipment}
    started = perf_counter()
    for violation in violations:
        for candidate in resolve_violation(demo_scene, violation["id"])["candidates"]:
            action = candidate["action"]
            assert action["type"] != "move_structure"
            assert action["target_id"] in furniture_ids
            assert candidate["verified"]
            assert candidate["new_violations"] == 0
    assert perf_counter() - started < 10


def test_diagonal_and_rotation_translation_candidates_are_verified():
    scene = Scene.model_validate({
        "meta": {"name": "Test", "room": {"min": [0, 0, 0], "max": [4, 4, 3]}},
        "rules": {}, "structures": [],
        "equipment": [
            {"id": "a", "name": "A", "type": "table", "box": {"min": [1, 1, 0], "max": [2, 2, 1]}},
            {"id": "b", "name": "B", "type": "table", "box": {"min": [1.8, 1.8, 0], "max": [2.8, 2.8, 1]}},
        ],
    })
    before = inspect_scene(scene)
    resolver = Resolver(scene, before["violations"][0], {_vkey(v) for v in before["violations"]})
    resolver.try_combined_moves("a")
    assert any(c["action"]["rotation_delta"] and all(c["action"]["translation_m"][:2]) for c in resolver.candidates)
    assert any(not c["action"]["rotation_delta"] and all(c["action"]["translation_m"][:2]) for c in resolver.candidates)
    for candidate in resolver.candidates:
        changed = apply_action(scene, candidate["action"])
        assert inspect_scene(changed)["violations"] == []
        assert changed.equipment[0].rotation == candidate["action"]["rotation_delta"]


def test_no_unsafe_fallback_when_room_is_full():
    scene = Scene.model_validate({
        "meta": {"name": "Test", "room": {"min": [0, 0, 0], "max": [1, 1, 3]}},
        "rules": {}, "structures": [],
        "equipment": [
            {"id": "a", "name": "A", "type": "table", "box": {"min": [0.1, 0.1, 0], "max": [0.9, 0.9, 1]}},
            {"id": "b", "name": "B", "type": "table", "box": {"min": [0.1, 0.1, 0], "max": [0.9, 0.9, 1]}},
        ],
    })
    assert resolve_violation(scene, "DE-101")["candidates"] == []
