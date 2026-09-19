"""Presentation-only translations; geometry and rule decisions stay language independent."""
from contextvars import ContextVar
import re


LANGUAGE: ContextVar[str] = ContextVar("language", default="ko")
TYPE_NAMES = {
    "bed": ("침대", "Bed"), "wardrobe": ("옷장", "Wardrobe"),
    "desk": ("책상", "Desk"), "sofa": ("소파", "Sofa"),
    "fridge": ("냉장고", "Refrigerator"), "bookshelf": ("책장", "Bookshelf"),
    "tv_stand": ("TV장", "TV stand"), "washing_machine": ("세탁기", "Washing machine"),
    "table": ("테이블", "Table"),
}
EN_NAMES = {
    "1인 주택 (거실·침실·서재, 9.6m x 6.0m)": "Single-person home (living room, bedroom, study; 9.6m x 6.0m)",
    "거실·주방": "Living room / kitchen", "거실": "Living room", "주방": "Kitchen",
    "침실": "Bedroom", "서재": "Study", "바닥": "Floor", "중앙": "Center",
    "벽 (거실-서재)": "Wall (living room / study)", "벽 (중앙)": "Central wall",
    "벽 (거실-침실)": "Wall (living room / bedroom)", "벽 (침실-서재)": "Wall (bedroom / study)",
    "현관문 개폐 구역": "Entrance door clearance",
    "침실문 개폐 구역": "Bedroom door clearance", "서재문 개폐 구역": "Study door clearance",
    "거실 창문 앞 구역": "Living room window clearance",
    "침실 창문 앞 구역": "Bedroom window clearance",
    "Room boundary": "Building boundary",
}


def tr(ko: str, en: str) -> str:
    return en if LANGUAGE.get() == "en" else ko


def short_name(name: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


def particle(name: str, pair: str) -> str:
    word = short_name(name)
    consonant, vowel = pair.split("/")
    last = ord(word[-1]) if word else 0
    has_final = 0xAC00 <= last <= 0xD7A3 and (last - 0xAC00) % 28 != 0
    return consonant if has_final else vowel


def with_particle(name: str, pair: str) -> str:
    return name + particle(name, pair)


def display_name(obj) -> str:
    name = obj.name
    if LANGUAGE.get() != "en":
        return "건물 외곽" if name == "Room boundary" else name
    if name in EN_NAMES:
        return EN_NAMES[name]
    for ko, en in TYPE_NAMES.values():
        if name == ko or name.startswith(ko + " ") or name.startswith(ko + "("):
            name = en + name[len(ko):]
            break
    for ko, en in EN_NAMES.items():
        name = name.replace(f"({ko})", f"({en})")
    return name


def direction(axis: str, sign: float) -> str:
    key = ("+" if sign > 0 else "-") + axis.upper()
    names = {"+X": "오른쪽", "-X": "왼쪽", "+Y": "위쪽", "-Y": "아래쪽",
             "+Z": "높이 위쪽", "-Z": "높이 아래쪽"}
    english = {"+X": "right", "-X": "left", "+Y": "up", "-Y": "down",
               "+Z": "upward", "-Z": "downward"}
    return tr(f"{names[key]}({key})", f"{english[key]} ({key})")


def violation_detail(code: str, a: dict, b: dict, measured: float, required: float) -> str:
    an, bn = a["name"], b["name"]
    if code == "HARD_CLASH":
        return tr(f"{with_particle(an, '과/와')} {bn} 충돌 (겹침 {abs(measured):.0f} mm)",
                  f"{an} overlaps {bn} by {abs(measured):.0f} mm")
    if code == "ZONE_INTRUSION":
        return tr(f"{with_particle(an, '이/가')} {with_particle(bn, '을/를')} {abs(measured):.0f} mm 침범",
                  f"{an} intrudes into {bn} by {abs(measured):.0f} mm")
    if code in ("MAINTENANCE_SPACE", "USAGE_SPACE"):
        return tr(f"{an} 사용 공간: {bn}까지 {measured:.0f} mm (필요 {required:.0f} mm)",
                  f"{an} usage space: {measured:.0f} mm to {bn}; {required:.0f} mm required")
    if code in ("OUT_OF_BOUNDS", "OUT_OF_ROOM"):
        return tr(f"{with_particle(an, '이/가')} {bn} 경계를 {abs(measured):.0f} mm 벗어남",
                  f"{an} extends outside {bn} by {abs(measured):.0f} mm")
    if code == "CLEARANCE_VIOLATION":
        return tr(f"{with_particle(an, '과/와')} {bn} 간격 {measured:.0f} mm (필요 {required:.0f} mm)",
                  f"{an} to {bn}: {measured:.0f} mm clearance; {required:.0f} mm required")
    if code == "CIRCULATION":
        return tr(f"현관에서 {an}까지 폭 {required:.0f} mm 동선 없음 (장애물: {bn})",
                  f"No {required:.0f} mm wide route from the entrance to {an} (obstacle: {bn})")
    raise ValueError(f"Missing violation translation: {code}")


def language_instruction() -> str:
    return tr("\n모든 사용자용 설명은 한국어로 작성하세요. 수치와 판정은 제공된 엔진 결과만 사용하세요.",
              "\nWrite all user-facing explanations in English. Use only engine-provided numbers and decisions.")
