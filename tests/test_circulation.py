from time import perf_counter

import numpy as np
import pytest

from backend.circulation import _grid, _mask, inspect_circulation, structure_role
from backend.detector import inspect_scene
from backend.models import Box, Equipment, Scene, Structure
from backend.usage import usage_spaces


@pytest.fixture
def corridor():
    return Scene.model_validate({
        "meta": {"name": "Test", "room": {"min": [0, 0, 0], "max": [4, 3, 3]}},
        "rules": {}, "equipment": [],
        "structures": [
            {"id": "entrance_swing", "name": "입구", "type": "zone",
             "box": {"min": [0, 1, 0], "max": [0.9, 1.9, 2]}},
            {"id": "far_door", "name": "방문", "type": "zone",
             "box": {"min": [3.1, 1, 0], "max": [4, 1.9, 2]}},
        ],
    })


def test_open_route_and_inferred_roles(corridor):
    result = inspect_circulation(corridor, [])
    assert result["targets"][0]["reachable"]
    assert result["paths"][0]["target_id"] == "far_door"
    path = result["paths"][0]["points"]
    for a, b in zip(path, path[1:]):
        assert abs(a[0] - b[0]) + abs(a[1] - b[1]) == pytest.approx(0.1)
    corridor.structures[1].role = "window"
    assert structure_role(corridor.structures[1]) == "window"
    assert inspect_circulation(corridor, [])["targets"] == []


def test_blocking_furniture_attribution(corridor):
    corridor.equipment.append(Equipment(id="blocker", name="책장", type="bookshelf",
        box=Box(min=[1.8, 0, 0], max=[2.2, 3, 2])))
    result = inspect_circulation(corridor, [])
    assert not result["targets"][0]["reachable"]
    assert result["targets"][0]["blocker"]["id"] == "blocker"
    corridor.equipment.clear()
    corridor.structures.append(Structure(id="wall", name="벽", type="wall",
        box=Box(min=[1.8, 0, 0], max=[2.2, 3, 2])))
    result = inspect_circulation(corridor, [])
    assert result["targets"][0]["blocker"]["id"] == "room"


def test_exact_half_width_clearance(corridor):
    box = Box(min=[1, 1, 0], max=[2, 2, 1])
    xx = np.array([[0.69, 0.7, 0.71]])
    yy = np.array([[1.5, 1.5, 1.5]])
    assert _mask(xx, yy, box).tolist() == [[False, False, True]]


def test_all_paths_avoid_inflated_obstacles(demo_scene):
    result = inspect_circulation(demo_scene, usage_spaces(demo_scene))
    room = demo_scene.meta.room
    xx, yy, blocked = _grid((room.min[0], room.min[1], room.max[0], room.max[1]))
    blocked = blocked.copy()
    for obj in demo_scene.equipment + [s for s in demo_scene.structures if s.type == "wall"]:
        blocked |= _mask(xx, yy, obj.box)
    for path in result["paths"]:
        for x, y, _ in path["points"]:
            ix, iy = int(round((x - 0.05) / 0.1)), int(round((y - 0.05) / 0.1))
            assert not blocked[iy, ix]
    full = inspect_scene(demo_scene)
    fast = inspect_scene(demo_scene, include_paths=False)
    assert full["violations"] == fast["violations"]
    assert full["summary"] == fast["summary"]


def test_demo_autofix_finishes_in_seconds(client):
    started = perf_counter()
    response = client.post("/api/autofix")
    elapsed = perf_counter() - started
    assert response.json()["inspection"]["summary"]["score"] == 100
    assert elapsed < 5.0, f"Autofix exceeded the five-second budget: {elapsed:.3f}s"
