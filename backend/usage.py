"""Axis-aligned access strips shared by inspection, circulation and visualization."""
from backend.i18n import display_name, tr
from backend.models import Scene


USAGE_RULES_MM = {
    "desk": 750, "wardrobe": 600, "fridge": 600, "washing_machine": 600, "bed": 300,
}
FRONTS = {0: (1, -1), 90: (0, 1), 180: (1, 1), 270: (0, -1)}
EPS = 1e-9


def usage_spaces(scene: Scene) -> list[dict]:
    spaces = []
    for furniture in scene.furniture:
        required = furniture.maintenance_clearance_mm
        if required is None:
            required = USAGE_RULES_MM.get(furniture.type)
        if required is None or required <= 0:
            continue
        if furniture.type == "bed":
            width = furniture.box.max[0] - furniture.box.min[0]
            depth = furniture.box.max[1] - furniture.box.min[1]
            axis = 1 if width >= depth else 0
            faces = [(axis, -1), (axis, 1)]
        else:
            faces = [FRONTS[furniture.rotation % 360]]
        alternatives = []
        for axis, sign in faces:
            cross = 1 - axis
            face = furniture.box.max[axis] if sign > 0 else furniture.box.min[axis]
            boundary = scene.meta.room.max[axis] if sign > 0 else scene.meta.room.min[axis]
            distance = max(0.0, (boundary - face) * sign)
            blocker = {"id": "room", "name": tr("건물 외곽", "Building boundary"), "kind": "structure"}
            obstacles = [(e, "furniture") for e in scene.furniture if e.id != furniture.id]
            obstacles += [(s, "structure") for s in scene.structures if s.type == "wall"]
            for obstacle, kind in obstacles:
                lo, hi = obstacle.box.min, obstacle.box.max
                if min(hi[cross], furniture.box.max[cross]) - max(lo[cross], furniture.box.min[cross]) <= EPS:
                    continue
                if min(hi[2], furniture.box.max[2]) - max(lo[2], furniture.box.min[2]) <= EPS:
                    continue
                far = hi[axis] if sign > 0 else lo[axis]
                if (far - face) * sign <= EPS:
                    continue
                near = lo[axis] if sign > 0 else hi[axis]
                gap = max(0.0, (near - face) * sign)
                if gap < distance:
                    distance = gap
                    blocker = {"id": obstacle.id, "name": display_name(obstacle), "kind": kind}
            low, high = list(furniture.box.min), list(furniture.box.max)
            end = face + sign * required / 1000
            low[axis], high[axis] = min(face, end), max(face, end)
            low[2], high[2] = 0.012, 0.022
            alternatives.append({
                "axis": axis, "sign": sign, "box": {"min": low, "max": high},
                "measured_mm": round(distance * 1000, 1), "blocker": blocker,
                "passed": distance * 1000 + 1e-6 >= required,
            })
        spaces.append({
            "id": furniture.id, "required_mm": required,
            "passed": any(s["passed"] for s in alternatives), "alternatives": alternatives,
        })
    return spaces
