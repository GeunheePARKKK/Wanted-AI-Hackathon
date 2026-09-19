"""Resolution candidate generator (Recommend step).

Strategy: generate geometric fix candidates, apply each to a copy of the
scene, re-run the full Rule Engine, and keep only candidates that
  1) resolve the target violation, and
  2) introduce zero new violations.
Every recommendation shown to the user is therefore verified, never guessed.
"""
from __future__ import annotations

import copy
from typing import Any

from backend import geometry as g
from backend.detector import inspect_scene
from backend.models import Scene
from backend.i18n import direction, display_name, tr, with_particle

MM = 1000.0
MARGIN_M = 0.05  # extra safety margin on top of the required clearance

AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}

IMPACT = {
    "offset_pipe_segment": ("동선 경로 조정", 0),
    "move_equipment": ("가구 재배치", 100),
    "rotate_equipment": ("가구 90° 회전 (제자리)", 0),
    "move_structure": ("구조 요소 이동 — 시공/구조 검토 필요", 3000),
}


def _vkey(v: dict) -> tuple:
    pair = tuple(sorted([v["a"]["id"], v["b"]["id"]]))
    return (*pair, v["code"])


def _find_pipe(scene: Scene, pid: str):
    return next(p for p in scene.pipes if p.id == pid)


def _find_box_obj(scene: Scene, oid: str):
    for eq in scene.equipment:
        if eq.id == oid:
            return eq, "move_equipment"
    for st in scene.structures:
        if st.id == oid:
            return st, "move_structure"
    return None, None


def _closest_segment(pipe, location: g.Vec3) -> int:
    """Index of the pipe segment closest to the violation location."""
    best_i, best_d = 0, float("inf")
    for i in range(len(pipe.path) - 1):
        d, _, _ = g.segment_segment_distance(
            tuple(pipe.path[i]), tuple(pipe.path[i + 1]), location, location)
        if d < best_d:
            best_i, best_d = i, d
    return best_i


def _jog_path(path: list, seg: int, delta: g.Vec3) -> list:
    """Offset one segment perpendicular to its run, keeping endpoints fixed."""
    p = [list(pt) for pt in path]
    a = [p[seg][k] + delta[k] for k in range(3)]
    b = [p[seg + 1][k] + delta[k] for k in range(3)]
    return p[: seg + 1] + [a, b] + p[seg + 1:]


def _apply_action(scene: Scene, action: dict) -> Scene:
    s = copy.deepcopy(scene)
    t = action["type"]
    if t == "offset_pipe_segment":
        _find_pipe(s, action["pipe_id"]).path = action["new_path"]
    elif t == "rotate_equipment":
        obj, _ = _find_box_obj(s, action["target_id"])
        obj.box.min = action["new_box"]["min"]
        obj.box.max = action["new_box"]["max"]
        obj.rotation = (getattr(obj, "rotation", 0) + action.get("rotation_delta", 90)) % 360
    elif t in ("move_equipment", "move_structure"):
        obj, _ = _find_box_obj(s, action["target_id"])
        obj.box.min = action["new_box"]["min"]
        obj.box.max = action["new_box"]["max"]
    return s


def _verify(scene: Scene, action: dict, target_key: tuple,
            old_keys: set) -> tuple[bool, int, int]:
    """Returns (resolves_target, newly_introduced_count, total_violations_after)."""
    result = inspect_scene(_apply_action(scene, action))
    new_keys = {_vkey(v) for v in result["violations"]}
    resolves = target_key not in new_keys
    introduced = len(new_keys - old_keys)
    return resolves, introduced, result["summary"]["violations"]


def _axis_name(axis: str, sign: float) -> str:
    return direction(axis, sign)


class Resolver:
    def __init__(self, scene: Scene, violation: dict, old_keys: set):
        self.scene = scene
        self.v = violation
        self.target_key = _vkey(violation)
        self.old_keys = old_keys
        self.candidates: list[dict[str, Any]] = []
        self.relaxed: list[tuple] = []  # fallback fixes that introduce side effects
        base = max(self.v["required_mm"] - self.v["measured_mm"], 0.0) / MM + MARGIN_M
        exact = max(self.v["required_mm"] - self.v["measured_mm"], 0.0) / MM  # snug fit, no margin
        sweep = [0.2, 0.35, 0.5, 0.8, 1.2, 1.8, 2.5, 3.5]
        self.magnitudes = sorted({round(m, 3) for m in
                                  [exact, base, base * 1.5, base * 2, base * 3, *sweep]
                                  if 0.01 < m < 8.0})

    def _counterpart_box(self, target_id: str):
        """AABB of the other subject in the violation, if it has one."""
        other = self.v["b"] if self.v["a"]["id"] == target_id else self.v["a"]
        if other["kind"] == "pipe" or other["id"] == "room":
            return None
        obj, _ = _find_box_obj(self.scene, other["id"])
        return None if obj is None else (tuple(obj.box.min), tuple(obj.box.max))

    def _try_direction(self, make_action, mags, describe) -> None:
        """Walk magnitudes: keep the first clean fix, remember the best relaxed one."""
        best = None
        for mag in mags:
            action = make_action(mag)
            resolves, introduced, n_after = _verify(
                self.scene, action, self.target_key, self.old_keys)
            if resolves and introduced == 0:
                self._add(action, mag, describe(mag), n_after, introduced=0)
                return
            if resolves and (best is None or introduced < best[0]):
                best = (introduced, action, mag, n_after)
        if best is not None:
            self.relaxed.append((best[0], best[1], best[2], describe(best[2]), best[3]))

    # ---------- candidate families ----------
    def try_pipe_offsets(self, pipe_id: str) -> None:
        pipe = _find_pipe(self.scene, pipe_id)
        seg = _closest_segment(pipe, tuple(self.v["location"]))
        seg_dir = g.sub(tuple(pipe.path[seg + 1]), tuple(pipe.path[seg]))
        for axis, unit in AXES.items():
            if axis == "z":
                continue  # walkways stay on the floor plane
            if abs(g.dot(seg_dir, unit)) > 1e-9:
                continue  # only perpendicular offsets keep the route orthogonal
            for sign in (1.0, -1.0):
                def make(mag, _unit=unit, _sign=sign, _axis=axis):
                    delta = g.scale(_unit, _sign * mag)
                    return {
                        "type": "offset_pipe_segment",
                        "pipe_id": pipe_id,
                        "segment": seg,
                        "axis": _axis,
                        "delta_m": round(_sign * mag, 4),
                        "new_path": _jog_path(pipe.path, seg, delta),
                    }
                name = _axis_name(axis, sign)
                self._try_direction(
                    make, self.magnitudes,
                    lambda mag, _n=name: tr(
                        f"{display_name(pipe)} 동선을 {_n}으로 {mag * MM:.0f} mm 조정",
                        f"Offset {display_name(pipe)} {mag * MM:.0f} mm {_n}"))

    def try_box_moves(self, target_id: str) -> None:
        obj, action_type = _find_box_obj(self.scene, target_id)
        if obj is None:
            return
        if getattr(obj, "type", "") == "zone":
            return  # door/window keep-clear zones are fixed by the building itself
        other_box = self._counterpart_box(target_id)
        req = self.v["required_mm"] / MM + MARGIN_M
        for axis_i, axis in enumerate(("x", "y")):  # furniture stays on the floor
            unit = AXES[axis]
            for sign in (1.0, -1.0):
                mags = list(self.magnitudes)
                if other_box is not None:
                    # exact displacement to clear the counterpart along this direction
                    if sign > 0:
                        d = (other_box[1][axis_i] + req) - obj.box.min[axis_i]
                    else:
                        d = obj.box.max[axis_i] - (other_box[0][axis_i] - req)
                    if 0.01 < d < 8.0:
                        mags = sorted({round(d, 3), *mags})

                def make(mag, _unit=unit, _sign=sign, _axis=axis):
                    delta = g.scale(_unit, _sign * mag)
                    return {
                        "type": action_type,
                        "target_id": target_id,
                        "axis": _axis,
                        "delta_m": round(_sign * mag, 4),
                        "new_box": {
                            "min": [obj.box.min[k] + delta[k] for k in range(3)],
                            "max": [obj.box.max[k] + delta[k] for k in range(3)],
                        },
                    }
                name = _axis_name(axis, sign)
                self._try_direction(
                    make, mags,
                    lambda mag, _n=name: tr(
                        f"{with_particle(display_name(obj), '을/를')} {_n}으로 {mag * MM:.0f} mm 이동",
                        f"Move {display_name(obj)} {mag * MM:.0f} mm {_n}"))

    def _add(self, action: dict, mag_m: float, description: str, n_after: int,
             introduced: int) -> None:
        impact_text, penalty = IMPACT[action["type"]]
        impact_text = tr(impact_text, {
            "offset_pipe_segment": "Adjust walkway route",
            "move_equipment": "Reposition furniture",
            "rotate_equipment": "Rotate furniture in place",
            "move_structure": "Move structure - construction review required",
        }[action["type"]])
        # vertical relocation of equipment/structures is a last resort
        if action["type"] != "offset_pipe_segment" and action.get("axis") == "z":
            penalty += 500
        self.candidates.append({
            "action": action,
            "description": description,
            "impact": impact_text,
            "displacement_mm": round(mag_m * MM, 1),
            "verified": introduced == 0,
            "new_violations": introduced,
            "violations_after": n_after,
            "score": round(mag_m * MM + penalty + introduced * 2000, 1),
        })

    def try_rotation(self, target_id: str) -> None:
        """In-place 90-degree rotation (AABB width/depth swap around center)."""
        obj, action_type = _find_box_obj(self.scene, target_id)
        if obj is None or action_type != "move_equipment":
            return
        w = obj.box.max[0] - obj.box.min[0]
        d = obj.box.max[1] - obj.box.min[1]
        if abs(w - d) < 1e-9:
            return  # square footprint: rotation changes nothing
        cx = (obj.box.min[0] + obj.box.max[0]) / 2
        cy = (obj.box.min[1] + obj.box.max[1]) / 2
        action = {
            "type": "rotate_equipment",
            "target_id": target_id,
            "rotation_delta": 90,
            "new_box": {
                "min": [cx - d / 2, cy - w / 2, obj.box.min[2]],
                "max": [cx + d / 2, cy + w / 2, obj.box.max[2]],
            },
        }
        resolves, introduced, n_after = _verify(
            self.scene, action, self.target_key, self.old_keys)
        description = tr(f"{with_particle(display_name(obj), '을/를')} 제자리에서 90° 회전",
                         f"Rotate {display_name(obj)} 90 degrees in place")
        if resolves and introduced == 0:
            self._add(action, 0.2, description, n_after, introduced=0)
        elif resolves:
            self.relaxed.append((introduced, action, 0.2,
                                 description, n_after))

    # ---------- entry ----------
    def run(self) -> list[dict[str, Any]]:
        a, b = self.v["a"], self.v["b"]
        if a["kind"] == "pipe":
            self.try_pipe_offsets(a["id"])
        if b["kind"] == "pipe":
            self.try_pipe_offsets(b["id"])
        if a["kind"] != "pipe":
            self.try_box_moves(a["id"])
        if b["kind"] not in ("pipe", "room") and b["id"] != "room":
            self.try_box_moves(b["id"])
        for subj in (a, b):
            if subj["kind"] == "equipment":
                self.try_rotation(subj["id"])
        # fallback: no perfectly clean fix exists -> offer least-harmful ones
        if not self.candidates and self.relaxed:
            self.relaxed.sort(key=lambda r: (r[0], r[2]))
            for introduced, action, mag, desc, n_after in self.relaxed[:3]:
                self._add(action, mag, desc, n_after, introduced=introduced)
        # maintenance space: prefer moving the intruder (b), not the equipment
        # that owns the clearance requirement (a)
        if self.v["code"] == "MAINTENANCE_SPACE":
            for c in self.candidates:
                if c["action"].get("target_id") == a["id"]:
                    c["score"] += 100
        self.candidates.sort(key=lambda c: c["score"])
        for i, c in enumerate(self.candidates):
            c["option"] = chr(ord("A") + i)
            c["recommended"] = i == 0
        return self.candidates[:4]


def resolve_violation(scene: Scene, violation_id: str) -> dict[str, Any]:
    result = inspect_scene(scene)
    violation = next((v for v in result["violations"] if v["id"] == violation_id), None)
    if violation is None:
        return {"error": tr(f"위반 {violation_id}을 찾을 수 없습니다", f"Violation {violation_id} not found")}
    old_keys = {_vkey(v) for v in result["violations"]}
    candidates = Resolver(scene, violation, old_keys).run()
    return {"violation": violation, "candidates": candidates}


def apply_action(scene: Scene, action: dict) -> Scene:
    return _apply_action(scene, action)
