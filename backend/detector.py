"""Rule Engine + clash/clearance detector.

Deterministic verification layer: every number reported here comes from
exact geometry (backend.geometry), never from an LLM.
"""
from __future__ import annotations

from typing import Any

from backend import geometry as g
from backend.models import Scene
from backend.i18n import display_name, tr, violation_detail
from backend.usage import usage_spaces
from backend.circulation import inspect_circulation

MM = 1000.0  # meters -> millimeters


def violation_penalty(severity: str, shortfall_mm: float) -> float:
    base, cap = {"HIGH": (10, 10), "MEDIUM": (4, 6)}[severity]
    return round(base + min(cap, max(shortfall_mm, 0) / 50), 1)


def _box(b) -> tuple[g.Vec3, g.Vec3]:
    return tuple(b.min), tuple(b.max)  # type: ignore[return-value]


def _subject(obj, kind: str) -> dict[str, Any]:
    return {"id": obj.id, "name": display_name(obj), "kind": kind}


class Inspector:
    def __init__(self, scene: Scene, include_paths: bool = True):
        self.scene = scene
        self.violations: list[dict[str, Any]] = []
        self.checks_run = 0
        self.usage = usage_spaces(scene)
        self.include_paths = include_paths

    # ---------------- helpers ----------------
    def _report(self, code: str, severity: str, a, b, measured_mm: float,
                required_mm: float, location: g.Vec3, detail: str) -> None:
        shortfall = max(required_mm - measured_mm, 0.0)
        self.violations.append({
            "id": f"DE-{len(self.violations) + 101}",
            "code": code,
            "severity": severity,
            "a": a,
            "b": b,
            "measured_mm": round(measured_mm, 1),
            "required_mm": round(required_mm, 1),
            "shortfall_mm": round(shortfall, 1),
            "penalty": violation_penalty(severity, shortfall),
            "location": [round(c, 3) for c in location],
            "detail": violation_detail(code, a, b, measured_mm, required_mm),
        })

    def _pipe_vs_box(self, pipe, obj, kind: str, required_mm: float) -> None:
        """Min surface distance between a pipe (capsule chain) and an AABB."""
        self.checks_run += 1
        r = pipe.diameter_mm / 2 / MM
        bmin, bmax = _box(obj.box)
        best = None
        for i in range(len(pipe.path) - 1):
            a_pt, b_pt = tuple(pipe.path[i]), tuple(pipe.path[i + 1])
            dist, p_seg, p_box = g.segment_box_distance(a_pt, b_pt, bmin, bmax)
            if best is None or dist < best[0]:
                best = (dist, p_seg, p_box)
        assert best is not None
        surface_mm = (best[0] - r) * MM
        loc = g.midpoint(best[1], best[2])
        if surface_mm <= 0:
            self._report(
                "HARD_CLASH", "HIGH",
                _subject(pipe, "pipe"), _subject(obj, kind),
                surface_mm, required_mm, loc,
                f"{pipe.id} penetrates {obj.id} (overlap {abs(surface_mm):.0f} mm)")
        elif surface_mm < required_mm:
            self._report(
                "CLEARANCE_VIOLATION", "MEDIUM",
                _subject(pipe, "pipe"), _subject(obj, kind),
                surface_mm, required_mm, loc,
                f"{pipe.id} to {obj.id} clearance {surface_mm:.0f} mm < required {required_mm:.0f} mm")

    # ---------------- checks ----------------
    def check_pipes_vs_structures(self) -> None:
        req = self.scene.rules.min_pipe_clearance_mm
        for pipe in self.scene.pipes:
            for st in self.scene.structures:
                if st.type == "zone":
                    continue  # walkways may pass through door/window zones
                self._pipe_vs_box(pipe, st, "structure", req)

    def check_pipes_vs_equipment(self) -> None:
        req = self.scene.rules.min_pipe_clearance_mm
        for pipe in self.scene.pipes:
            connected = {pipe.from_, pipe.to}
            for eq in self.scene.equipment:
                if eq.id in connected:
                    continue  # a pipe may touch the equipment it connects to
                self._pipe_vs_box(pipe, eq, "equipment", req)

    def check_pipes_vs_pipes(self) -> None:
        req = self.scene.rules.min_pipe_to_pipe_clearance_mm
        if req <= 0:
            return  # walkways are allowed to cross each other
        pipes = self.scene.pipes
        for i in range(len(pipes)):
            for j in range(i + 1, len(pipes)):
                p1, p2 = pipes[i], pipes[j]
                self.checks_run += 1
                r_sum = (p1.diameter_mm + p2.diameter_mm) / 2 / MM
                best = None
                for s in range(len(p1.path) - 1):
                    for t in range(len(p2.path) - 1):
                        dist, c1, c2 = g.segment_segment_distance(
                            tuple(p1.path[s]), tuple(p1.path[s + 1]),
                            tuple(p2.path[t]), tuple(p2.path[t + 1]))
                        if best is None or dist < best[0]:
                            best = (dist, c1, c2)
                assert best is not None
                surface_mm = (best[0] - r_sum) * MM
                loc = g.midpoint(best[1], best[2])
                if surface_mm <= 0:
                    self._report(
                        "HARD_CLASH", "HIGH",
                        _subject(p1, "pipe"), _subject(p2, "pipe"),
                        surface_mm, req, loc,
                        f"{p1.id} and {p2.id} intersect (overlap {abs(surface_mm):.0f} mm)")
                elif surface_mm < req:
                    self._report(
                        "CLEARANCE_VIOLATION", "MEDIUM",
                        _subject(p1, "pipe"), _subject(p2, "pipe"),
                        surface_mm, req, loc,
                        f"{p1.id} to {p2.id} clearance {surface_mm:.0f} mm < required {req:.0f} mm")

    def check_equipment_overlaps(self) -> None:
        objs = [(eq, "equipment") for eq in self.scene.equipment] + \
               [(st, "structure") for st in self.scene.structures if st.type != "deck"]
        for i in range(len(objs)):
            for j in range(i + 1, len(objs)):
                (a, ka), (b, kb) = objs[i], objs[j]
                if ka == "structure" and kb == "structure":
                    continue
                self.checks_run += 1
                amin, amax = _box(a.box)
                bmin, bmax = _box(b.box)
                if g.boxes_overlap(amin, amax, bmin, bmax):
                    # penetration depth = smallest axis overlap (how far to move to separate)
                    depth = min(min(amax[i], bmax[i]) - max(amin[i], bmin[i]) for i in range(3))
                    ca = g.clamp_to_box(g.midpoint(bmin, bmax), amin, amax)
                    zone = next((o for o, k in ((a, ka), (b, kb))
                                 if k == "structure" and o.type == "zone"), None)
                    if zone is not None:
                        other = b if zone is a else a
                        self._report(
                            "ZONE_INTRUSION", "MEDIUM",
                            _subject(a, ka), _subject(b, kb),
                            -depth * MM, 0.0, ca,
                            f"{other.id}이(가) {zone.name}을 {depth * MM:.0f} mm 침범")
                    else:
                        self._report(
                            "HARD_CLASH", "HIGH",
                            _subject(a, ka), _subject(b, kb),
                            -depth * MM, 0.0, ca,
                            f"{a.id} overlaps {b.id} (penetration {depth * MM:.0f} mm)")

    def check_maintenance_space(self) -> None:
        for space in self.usage:
            self.checks_run += 1
            if space["passed"]:
                continue
            eq = next(e for e in self.scene.equipment if e.id == space["id"])
            best = max(space["alternatives"], key=lambda s: s["measured_mm"])
            box = best["box"]
            self._report("USAGE_SPACE", "MEDIUM", _subject(eq, "equipment"),
                         best["blocker"], best["measured_mm"], space["required_mm"],
                         g.midpoint(tuple(box["min"]), tuple(box["max"])), "")

    def check_bounds(self) -> None:
        """Objects must stay inside the room (rejects fixes that push things through the hull)."""
        rmin, rmax = _box(self.scene.meta.room)
        for pipe in self.scene.pipes:
            self.checks_run += 1
            r = pipe.diameter_mm / 2 / MM
            worst = None
            for pt in pipe.path:
                for i in range(3):
                    over = max(rmin[i] + r - pt[i], pt[i] - (rmax[i] - r), 0.0)
                    if over > 0 and (worst is None or over > worst[0]):
                        worst = (over, tuple(pt))
            if worst:
                self._report(
                    "OUT_OF_BOUNDS", "HIGH",
                    _subject(pipe, "pipe"),
                    {"id": "room", "name": tr("건물 외곽", "Building boundary"), "kind": "structure"},
                    -worst[0] * MM, 0.0, worst[1],
                    f"{pipe.id} exits the room boundary by {worst[0] * MM:.0f} mm")
        for eq in self.scene.equipment + self.scene.structures:
            if getattr(eq, "type", "") == "deck":
                continue
            self.checks_run += 1
            emin, emax = _box(eq.box)
            over = max(max(rmin[i] - emin[i], emax[i] - rmax[i], 0.0) for i in range(3))
            if over > 0:
                self._report(
                    "OUT_OF_BOUNDS", "HIGH",
                    _subject(eq, "equipment"),
                    {"id": "room", "name": tr("건물 외곽", "Building boundary"), "kind": "structure"},
                    -over * MM, 0.0, g.midpoint(emin, emax),
                    f"{eq.id} exits the room boundary by {over * MM:.0f} mm")

    def check_room_containment(self) -> None:
        """Furniture must sit fully inside one room (not straddle walls/gaps)."""
        rooms = self.scene.rooms
        if not rooms:
            return
        for eq in self.scene.equipment:
            self.checks_run += 1
            emin, emax = _box(eq.box)
            best = None  # (overhang_m, room) for the best-fitting room
            for r in rooms:
                rmin, rmax = _box(r.box)
                overhang = max(max(rmin[i] - emin[i], emax[i] - rmax[i], 0.0)
                               for i in range(2))  # x/y only; rooms are full height
                if best is None or overhang < best[0]:
                    best = (overhang, r)
            over, room = best
            if over > 1e-9:
                self._report(
                    "OUT_OF_ROOM", "HIGH",
                    _subject(eq, "equipment"),
                    {"id": room.id, "name": display_name(room), "kind": "room"},
                    -over * MM, 0.0, g.midpoint(emin, emax),
                    f"{eq.id}이(가) {room.name} 영역을 {over * MM:.0f} mm 벗어남")

    # ---------------- entry ----------------
    def run(self) -> dict[str, Any]:
        self.check_pipes_vs_structures()
        self.check_pipes_vs_equipment()
        self.check_pipes_vs_pipes()
        self.check_equipment_overlaps()
        self.check_maintenance_space()
        self.check_room_containment()
        self.check_bounds()
        circulation = inspect_circulation(self.scene, self.usage, self.include_paths)
        for result in circulation["targets"]:
            self.checks_run += 1
            if not result["reachable"]:
                target = result["target"]
                obj = next(o for o in self.scene.equipment + self.scene.structures if o.id == target["id"])
                self._report("CIRCULATION", "HIGH", target, result["blocker"], 0, 600,
                             g.midpoint(tuple(obj.box.min), tuple(obj.box.max)), "")
        by_sev = {"HIGH": 0, "MEDIUM": 0}
        for v in self.violations:
            by_sev[v["severity"]] += 1
        score = round(max(0, 100 - sum(v["penalty"] for v in self.violations)), 1)
        return {
            "summary": {
                "checks_run": self.checks_run,
                "violations": len(self.violations),
                "passed": self.checks_run - len(self.violations),
                "by_severity": by_sev,
                "score": score,
            },
            "violations": self.violations,
            "usage_spaces": self.usage,
            "circulation": circulation,
        }


def inspect_scene(scene: Scene, include_paths: bool = True) -> dict[str, Any]:
    return Inspector(scene, include_paths).run()
