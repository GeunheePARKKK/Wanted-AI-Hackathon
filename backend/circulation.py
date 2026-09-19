"""600 mm pedestrian clearance on a vectorized 100 mm floor grid."""
from collections import deque
from functools import lru_cache

import numpy as np

from backend.i18n import display_name, tr
from backend.models import Scene


CELL = 0.1
RADIUS = 0.3


def structure_role(obj) -> str | None:
    if obj.role:
        return obj.role
    if "entrance" in obj.id:
        return "entrance"
    if "door" in obj.id:
        return "door"
    if "window" in obj.id:
        return "window"
    return None


@lru_cache(maxsize=16)
def _grid(bounds: tuple):
    xmin, ymin, xmax, ymax = bounds
    x = np.arange(xmin + CELL / 2, xmax, CELL)
    y = np.arange(ymin + CELL / 2, ymax, CELL)
    xx, yy = np.meshgrid(x, y)
    outside = ((xx - xmin < RADIUS - 1e-9) | (xmax - xx < RADIUS - 1e-9) |
               (yy - ymin < RADIUS - 1e-9) | (ymax - yy < RADIUS - 1e-9))
    return xx, yy, outside


def _mask(xx, yy, box):
    lo, hi = box.min, box.max
    dx = np.maximum(np.maximum(lo[0] - xx, xx - hi[0]), 0)
    dy = np.maximum(np.maximum(lo[1] - yy, yy - hi[1]), 0)
    return dx * dx + dy * dy < RADIUS * RADIUS - 1e-10


def _inside(xx, yy, low, high):
    return ((xx >= low[0] - 1e-9) & (xx <= high[0] + 1e-9) &
            (yy >= low[1] - 1e-9) & (yy <= high[1] + 1e-9))


def _bfs(blocked, starts, nx, previous=None):
    parents = previous.copy() if previous is not None else [-1] * blocked.size
    free = (~blocked).ravel().tolist()
    reached = np.array(parents) >= 0
    if reached.any():
        adjacent = np.zeros(blocked.size, dtype=bool)
        adjacent[1:] |= reached[:-1]
        adjacent[:-1] |= reached[1:]
        adjacent[nx:] |= reached[:-nx]
        adjacent[:-nx] |= reached[nx:]
        seeds = np.flatnonzero(adjacent & ~reached & (~blocked).ravel())
        queue = deque(int(i) for i in seeds)
        for i in queue:
            parents[i] = i
    else:
        choices = [int(i) for i in starts if free[int(i)]]
        if not choices:
            return parents
        start = choices[0]
        parents[start] = start
        queue = deque([start])
    while queue:
        current = queue.popleft()
        for nxt in (current - 1, current + 1, current - nx, current + nx):
            # The building's 300 mm boundary strip always blocks the grid edges.
            if 0 <= nxt < len(parents) and free[nxt] and parents[nxt] < 0:
                parents[nxt] = current
                queue.append(nxt)
    return parents


def inspect_circulation(scene: Scene, usage: list[dict], include_paths: bool = True) -> dict:
    entrance = next((s for s in scene.structures if structure_role(s) == "entrance"), None)
    if entrance is None:
        return {"enabled": False, "reason": tr("현관 구역 없음", "No entrance region"), "targets": [], "paths": []}
    room = scene.meta.room
    xx, yy, outside = _grid((room.min[0], room.min[1], room.max[0], room.max[1]))
    nx = xx.shape[1]
    static = outside.copy()
    for wall in scene.structures:
        if wall.type == "wall":
            static |= _mask(xx, yy, wall.box)
    furniture_masks = [_mask(xx, yy, e.box) for e in scene.equipment]
    counts = np.zeros(xx.shape, dtype=np.int32)
    for mask in furniture_masks:
        counts += mask
    blocked = static | (counts > 0)
    entrance_cells = np.flatnonzero(_inside(xx, yy, entrance.box.min, entrance.box.max))
    cx = (entrance.box.min[0] + entrance.box.max[0]) / 2
    cy = (entrance.box.min[1] + entrance.box.max[1]) / 2
    entrance_cells = sorted(entrance_cells, key=lambda i: (xx.ravel()[i]-cx)**2 + (yy.ravel()[i]-cy)**2)
    targets = []
    for door in scene.structures:
        if structure_role(door) == "door":
            targets.append(({"id": door.id, "name": display_name(door), "kind": "structure"},
                            _inside(xx, yy, door.box.min, door.box.max)))
    for space in usage:
        obj = next(e for e in scene.equipment if e.id == space["id"])
        mask = np.zeros(xx.shape, dtype=bool)
        for side in space["alternatives"]:
            low, high = list(side["box"]["min"]), list(side["box"]["max"])
            axis, sign = side["axis"], side["sign"]
            face = obj.box.max[axis] if sign > 0 else obj.box.min[axis]
            end = face + sign * max(space["required_mm"] / 1000, 0.6)
            low[axis], high[axis] = min(face, end), max(face, end)
            mask |= _inside(xx, yy, low, high)
        targets.append(({"id": obj.id, "name": display_name(obj), "kind": "equipment"}, mask))
    parents = _bfs(blocked, entrance_cells, nx)
    reachable = np.array(parents).reshape(xx.shape) >= 0
    results, paths, failures = [], [], []
    for subject, mask in targets:
        hits = np.flatnonzero(mask & reachable)
        result = {"target": subject, "reachable": bool(hits.size)}
        results.append(result)
        if not hits.size:
            failures.append((result, mask))
            continue
        if not include_paths:
            continue
        idx = int(hits[0])
        path = []
        while True:
            path.append([round(float(xx.ravel()[idx]), 3), round(float(yy.ravel()[idx]), 3), 0.03])
            if parents[idx] == idx:
                break
            idx = parents[idx]
        paths.append({"target_id": subject["id"], "points": path[::-1]})
    unresolved = list(failures)
    for furniture, mask in zip(scene.equipment, furniture_masks):
        if not unresolved:
            break
        without = static | ((counts - mask) > 0)
        reachable_without = np.array(_bfs(without, entrance_cells, nx, parents)).reshape(xx.shape) >= 0
        for result, target_mask in list(unresolved):
            if np.any(target_mask & reachable_without):
                result["blocker"] = {"id": furniture.id, "name": display_name(furniture), "kind": "equipment"}
                unresolved.remove((result, target_mask))
    for result, _ in unresolved:
        result["blocker"] = {"id": "room", "name": tr("고정 구조 또는 여러 장애물", "Fixed structure or multiple obstacles"),
                             "kind": "structure"}
    return {"enabled": True, "cell_mm": 100, "width_mm": 600, "targets": results, "paths": paths}
