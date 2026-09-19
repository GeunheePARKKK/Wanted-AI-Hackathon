"""Natural-language design commands (LLM copilot mode).

The LLM translates a Korean request into a list of structured ops;
all geometry mutation is done here in plain Python, then the rule
engine re-inspects. The LLM never edits the scene directly.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from backend.llm import _call_claude
from backend.models import Box, Equipment, Pipe, Scene, Structure
from backend.i18n import TYPE_NAMES, display_name, language_instruction, tr

TYPE_SIZES = {
    "bed": [2.0, 1.1, 0.5], "wardrobe": [1.2, 0.6, 2.0], "desk": [1.2, 0.6, 0.75],
    "sofa": [1.8, 0.85, 0.8], "fridge": [0.7, 0.7, 1.8], "bookshelf": [0.8, 0.3, 1.8],
    "tv_stand": [1.5, 0.4, 0.5], "washing_machine": [0.6, 0.6, 0.85], "table": [1.2, 0.8, 0.72],
}

PROMPT = """당신은 1인 주택(거실·침실·서재) 가구 배치 CAD 어시스턴트입니다. 현재 배치 상태(단위: 미터, Z-up, 가구는 바닥 z=0에 놓임):
{scene}

사용자 요청: "{text}"

사용 가능한 작업(ops) 목록:
- {{"op":"add_equipment","type":"bed|wardrobe|desk|sofa|fridge|bookshelf|tv_stand|washing_machine|table","center":[x,y]}}
- {{"op":"move","id":"<객체id>","delta":[dx,dy,dz]}}
- {{"op":"rotate","id":"<가구id>"}}  (제자리 90° 회전)
- {{"op":"delete","id":"<객체id>"}}

규칙:
- 가구는 반드시 하나의 방(rooms 중 하나) 경계 안에 완전히 들어가도록 좌표를 계산할 것
- 기존 가구의 box와 겹치지 않게 배치할 것
- 문 개폐 구역(zone)과 창문 앞 구역은 비워둘 것
- 존재하는 id만 참조할 것

순수 JSON만 출력 (코드블록 금지):
{{"ops":[...], "reply":"수행한 내용을 선택된 언어로 한 문장으로"}}"""


def _brief(scene: Scene) -> str:
    return json.dumps({
        "room": scene.meta.room.model_dump(),
        "rooms": [{"id": r.id, "name": r.name, "box": r.box.model_dump()}
                  for r in scene.rooms],
        "equipment": [{"id": e.id, "type": e.type, "box": e.box.model_dump()}
                      for e in scene.equipment],
        "structures": [{"id": s.id, "type": s.type, "box": s.box.model_dump()}
                       for s in scene.structures],
        "pipes": [{"id": p.id, "diameter_mm": p.diameter_mm, "path": p.path}
                  for p in scene.pipes],
    }, ensure_ascii=False)


def _next_id(scene: Scene, prefix: str) -> str:
    ids = {e.id for e in scene.equipment} | {s.id for s in scene.structures} | \
          {p.id for p in scene.pipes}
    n = 1
    while f"{prefix}_{n}" in ids:
        n += 1
    return f"{prefix}_{n}"


def _next_pipe_id(scene: Scene) -> str:
    ids = {p.id for p in scene.pipes}
    n = 1
    while f"W-{n}" in ids:
        n += 1
    return f"W-{n}"


def _find(scene: Scene, oid: str):
    for coll, kind in ((scene.equipment, "equipment"),
                       (scene.structures, "structure"),
                       (scene.pipes, "pipe")):
        for o in coll:
            if o.id == oid:
                return o, kind, coll
    raise ValueError(tr(f"객체 '{oid}' 없음", f"Object '{oid}' not found"))


def _apply_op(s: Scene, op: dict) -> str:
    k = op["op"]
    if k == "add_equipment":
        t = op["type"]
        size = op.get("size") or TYPE_SIZES[t]
        cx, cy = float(op["center"][0]), float(op["center"][1])
        eid = op.get("id") or _next_id(s, t)
        number = 1 + sum(e.type == t for e in s.equipment)
        s.equipment.append(Equipment(id=eid, name=f"{TYPE_NAMES[t][0]} {number}", type=t, box=Box(
            min=[cx - size[0] / 2, cy - size[1] / 2, 0],
            max=[cx + size[0] / 2, cy + size[1] / 2, size[2]])))
        return tr(f"{s.equipment[-1].name} 추가", f"Added {display_name(s.equipment[-1])}")
    if k == "add_frame":
        x = float(op["x"])
        fid = op.get("id") or _next_id(s, "frame")
        h = s.meta.room.max[2]
        s.structures.append(Structure(id=fid, name=fid, type="frame", box=Box(
            min=[x - 0.1, 0, 0], max=[x + 0.1, 0.4, h])))
        return tr(f"{fid} 추가", f"Added {fid}")
    if k == "move":
        o, kind, _ = _find(s, op["id"])
        d = [float(v) for v in op["delta"]]
        if kind == "pipe":
            o.path = [[p[i] + d[i] for i in range(3)] for p in o.path]
        else:
            o.box.min = [o.box.min[i] + d[i] for i in range(3)]
            o.box.max = [o.box.max[i] + d[i] for i in range(3)]
        return tr(f"{display_name(o)} 이동", f"Moved {display_name(o)}")
    if k == "rotate":
        o, kind, _ = _find(s, op["id"])
        if kind != "equipment":
            raise ValueError(tr(f"{display_name(o)}는 회전할 수 없습니다", f"Cannot rotate {display_name(o)}"))
        cx = (o.box.min[0] + o.box.max[0]) / 2
        cy = (o.box.min[1] + o.box.max[1]) / 2
        w = o.box.max[0] - o.box.min[0]
        d = o.box.max[1] - o.box.min[1]
        o.box.min = [cx - d / 2, cy - w / 2, o.box.min[2]]
        o.box.max = [cx + d / 2, cy + w / 2, o.box.max[2]]
        o.rotation = (getattr(o, "rotation", 0) + 90) % 360
        return tr(f"{display_name(o)} 90° 회전", f"Rotated {display_name(o)} 90 degrees")
    if k == "delete":
        o, _, coll = _find(s, op["id"])
        coll.remove(o)
        return tr(f"{display_name(o)} 삭제", f"Deleted {display_name(o)}")
    if k == "add_pipe":
        pid = op.get("id") or _next_pipe_id(s)
        path = [[float(c) for c in pt] for pt in op["path"]]
        if len(path) < 2:
            raise ValueError(tr("경유점 2개 이상 필요", "At least two waypoints are required"))
        s.pipes.append(Pipe(id=pid, name=pid, system="walkway",
                            diameter_mm=float(op.get("diameter_mm", 80)), path=path))
        return tr(f"{pid} 추가", f"Added {pid}")
    if k == "set_diameter":
        o, kind, _ = _find(s, op["id"])
        if kind != "pipe":
            raise ValueError(tr(f"{display_name(o)}는 동선이 아님", f"{display_name(o)} is not a walkway"))
        o.diameter_mm = float(op["diameter_mm"])
        return tr(f"{display_name(o)} 폭 변경", f"Changed width of {display_name(o)}")
    raise ValueError(tr(f"알 수 없는 op '{k}'", f"Unknown op '{k}'"))


def run_command(scene: Scene, text: str) -> dict[str, Any]:
    out = _call_claude(PROMPT.format(scene=_brief(scene), text=text) + language_instruction())
    if out is None:
        return {"error": tr("AI 호출에 실패했습니다. AI 제공자 설정을 확인하세요.",
                            "AI request failed. Check your AI provider configuration.")}
    s = copy.deepcopy(scene)
    done, errors = [], []
    for op in out.get("ops") or []:
        try:
            done.append(_apply_op(s, op))
        except Exception as e:  # keep applying the rest
            errors.append(f"{op.get('op', '?')}: {e}")
    return {
        "scene": s if done else None,
        "reply": out.get("reply", ""),
        "applied": done,
        "errors": errors,
    }
