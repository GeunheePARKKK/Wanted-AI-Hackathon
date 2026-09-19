"""Deterministic room placement; no coordinates are supplied by the language model."""
import math

import numpy as np

from backend.detector import inspect_scene
from backend.i18n import TYPE_NAMES, display_name, tr
from backend.models import Box, Furniture, Scene
from backend.resolver import _vkey
from backend.usage import usage_spaces


MAX_FULL_CHECKS = 64


def place(scene: Scene, op: dict, sizes: dict) -> str:
    room = next((r for r in scene.rooms if r.id == op["room"]), None)
    if room is None:
        raise ValueError(tr("배치할 방이 없습니다.", "Placement room not found."))
    if bool(op.get("id")) == bool(op.get("type")):
        raise ValueError("place requires exactly one of id or type")
    existing = next((e for e in scene.furniture if e.id == op.get("id")), None)
    if op.get("id") and existing is None:
        raise ValueError(tr("배치할 가구가 없습니다.", "Furniture to place was not found."))
    if existing is None:
        kind = op["type"]
        if kind not in sizes:
            raise ValueError(tr("지원하지 않는 가구 종류입니다.", "Unsupported furniture type."))
        number = 1
        used = {o.id for o in scene.furniture + scene.structures + scene.walkways}
        while f"{kind}_{number}" in used:
            number += 1
        name_number = 1
        names = {e.name for e in scene.furniture if e.type == kind}
        if names:
            name_number = 2
        while f"{TYPE_NAMES[kind][0]} {name_number}" in names:
            name_number += 1
        existing = Furniture(id=f"{kind}_{number}", name=f"{TYPE_NAMES[kind][0]} {name_number}",
                             type=kind, box=Box(min=[0, 0, 0], max=list(sizes[kind])))
        creating = True
    else:
        creating = False
    near = None
    if op.get("near"):
        near = next((o for o in scene.furniture + scene.structures if o.id == op["near"]), None)
        if near is None:
            raise ValueError(tr("가까이 둘 대상이 없습니다.", "The near target was not found."))
    target = near.box if near else room.box
    center = [(target.min[i] + target.max[i]) / 2 for i in range(2)]
    old_keys = {_vkey(v) for v in inspect_scene(scene, include_paths=False)["violations"]}
    obstacles = [e for e in scene.furniture if e.id != existing.id]
    obstacles += [s for s in scene.structures if s.type != "deck"]
    original_size = [existing.box.max[i] - existing.box.min[i] for i in range(3)]
    candidates = []
    for rotation in (0, 90, 180, 270):
        w, d, h = original_size
        if (rotation - existing.rotation) % 180:
            w, d = d, w
        lo, hi = room.box.min, room.box.max
        if h > hi[2] or w > hi[0] - lo[0] or d > hi[1] - lo[1]:
            continue
        x = np.arange(math.ceil((lo[0] + w/2) * 10) / 10, hi[0] - w/2 + 1e-9, 0.1)
        y = np.arange(math.ceil((lo[1] + d/2) * 10) / 10, hi[1] - d/2 + 1e-9, 0.1)
        xx, yy = np.meshgrid(x, y)
        valid = np.ones(xx.shape, dtype=bool)
        for obj in obstacles:
            if obj.box.min[2] >= h or obj.box.max[2] <= 0:
                continue
            valid &= ~((xx + w/2 >= obj.box.min[0] - 1e-9) & (xx - w/2 <= obj.box.max[0] + 1e-9) &
                       (yy + d/2 >= obj.box.min[1] - 1e-9) & (yy - d/2 <= obj.box.max[1] + 1e-9))
        for cx, cy in zip(xx[valid], yy[valid]):
            distance = (cx - center[0])**2 + (cy - center[1])**2
            candidates.append((float(distance), rotation, float(cx), float(cy), w, d, h))
    candidates.sort()
    checked = 0
    for _, rotation, cx, cy, w, d, h in candidates:
        candidate = scene.model_copy(deep=True)
        obj = existing.model_copy(deep=True)
        obj.rotation = rotation
        obj.box = Box(min=[cx-w/2, cy-d/2, 0], max=[cx+w/2, cy+d/2, h])
        candidate.furniture = [e for e in candidate.furniture if e.id != obj.id] + [obj]
        own_usage = next((s for s in usage_spaces(candidate) if s["id"] == obj.id), None)
        if own_usage is not None and not own_usage["passed"]:
            continue
        checked += 1
        keys = {_vkey(v) for v in inspect_scene(candidate, include_paths=False)["violations"]}
        if not keys - old_keys:
            if creating:
                scene.furniture.append(obj)
            else:
                index = next(i for i, e in enumerate(scene.furniture) if e.id == obj.id)
                scene.furniture[index] = obj
            return tr(f"{display_name(obj)} 배치", f"Placed {display_name(obj)}")
        if checked >= MAX_FULL_CHECKS:
            break
    raise ValueError(tr(f"안전한 배치 위치를 찾지 못했습니다 (전체 검사 {checked}회).",
                        f"No safe placement found ({checked} full checks)."))
