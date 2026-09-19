import pytest

from backend.detector import inspect_scene
from backend.models import Box, Equipment, Scene, Structure
from backend.usage import usage_spaces


@pytest.fixture
def usage_scene():
    return Scene.model_validate({
        "meta": {"name": "Test", "room": {"min": [0, 0, 0], "max": [6, 6, 3]}},
        "rules": {}, "structures": [],
        "equipment": [{"id": "desk", "name": "책상", "type": "desk",
                       "box": {"min": [2, 2, 0], "max": [3, 3, 1]}}],
    })


@pytest.mark.parametrize("rotation,low,high", [
    (0, [2, 1.3, 0], [3, 1.6, 1]), (90, [3.4, 2, 0], [3.7, 3, 1]),
    (180, [2, 3.4, 0], [3, 3.7, 1]), (270, [1.3, 2, 0], [1.6, 3, 1]),
])
def test_front_direction_at_each_rotation(usage_scene, rotation, low, high):
    usage_scene.equipment[0].rotation = rotation
    usage_scene.equipment.append(Equipment(id="blocker", name="장애물", type="table",
                                         box=Box(min=low, max=high)))
    violations = [v for v in inspect_scene(usage_scene)["violations"] if v["code"] == "USAGE_SPACE"]
    assert len(violations) == 1
    assert violations[0]["measured_mm"] == 400
    assert violations[0]["b"]["id"] == "blocker"


def test_side_furniture_does_not_block_front(usage_scene):
    usage_scene.equipment.append(Equipment(id="side", name="책장", type="bookshelf",
        box=Box(min=[3.1, 2, 0], max=[3.5, 3, 1])))
    assert usage_spaces(usage_scene)[0]["passed"] is True


@pytest.mark.parametrize("kind,blocked", [("wall", True), ("zone", False), ("deck", False)])
def test_only_walls_block_usage(usage_scene, kind, blocked):
    usage_scene.structures.append(Structure(id="obstacle", name="구조물", type=kind,
        box=Box(min=[2, 1.3, 0], max=[3, 1.6, 2])))
    assert usage_spaces(usage_scene)[0]["passed"] is not blocked


def test_boundary_and_override(usage_scene):
    eq = usage_scene.equipment[0]
    eq.box.min[1], eq.box.max[1] = 0.5, 1.5
    space = usage_spaces(usage_scene)[0]
    assert space["passed"] is False
    assert space["alternatives"][0]["blocker"]["id"] == "room"
    eq.maintenance_clearance_mm = 500
    assert usage_spaces(usage_scene)[0]["passed"] is True


def test_bed_needs_only_one_long_side(usage_scene):
    bed = usage_scene.equipment[0]
    bed.type = "bed"
    bed.box = Box(min=[1, 0.1, 0], max=[3, 1.1, 0.5])
    sides = usage_spaces(usage_scene)[0]
    assert sides["passed"]
    assert [s["passed"] for s in sides["alternatives"]] == [False, True]
    usage_scene.structures.append(Structure(id="wall", name="벽", type="wall",
        box=Box(min=[1, 1.3, 0], max=[3, 1.4, 2])))
    assert not usage_spaces(usage_scene)[0]["passed"]
    violation = next(v for v in inspect_scene(usage_scene)["violations"] if v["code"] == "USAGE_SPACE")
    assert violation["measured_mm"] == 200


@pytest.mark.parametrize("kind,required", [("fridge", 600), ("washing_machine", 600),
                                        ("wardrobe", 600), ("desk", 750)])
def test_type_defaults(usage_scene, kind, required):
    usage_scene.equipment[0].type = kind
    assert usage_spaces(usage_scene)[0]["required_mm"] == required
