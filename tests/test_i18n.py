import pytest

from backend import chat, commands, llm
from backend.i18n import LANGUAGE, particle, short_name


@pytest.mark.parametrize("name,pair,expected", [
    ("소파 (거실)", "을/를", "를"), ("소파 (거실)", "이/가", "가"),
    ("옷장 (침실)", "을/를", "을"), ("책상 (서재)", "이/가", "이"),
    ("책상 (서재)", "과/와", "과"), ("소파 (거실)", "과/와", "와"),
])
def test_particles_ignore_parentheses(name, pair, expected):
    assert particle(name, pair) == expected
    assert "(" not in short_name(name)


def test_languages_change_only_presentation(client):
    ko = client.get("/api/inspect").json()
    en = client.get("/api/inspect?lang=en").json()
    assert ko["summary"] == en["summary"]
    assert ko["violations"][0]["a"]["name"] == "소파 (거실)"
    assert en["violations"][0]["a"]["name"] == "Sofa (Living room)"
    for a, b in zip(ko["violations"], en["violations"]):
        for key in ("id", "code", "severity", "measured_mm", "required_mm", "location"):
            assert a[key] == b[key]
        assert a["detail"] != b["detail"]
    assert client.get("/api/inspect").json() == ko
    assert client.get("/api/inspect?lang=fr").status_code == 422
    target = ko["violations"][0]["id"]
    ko_fix = client.get(f"/api/resolve/{target}").json()["candidates"][0]
    en_fix = client.get(f"/api/resolve/{target}?lang=en").json()["candidates"][0]
    assert ko_fix["action"] == en_fix["action"]
    assert ko_fix["description"] != en_fix["description"]
    assert "sofa" not in ko_fix["description"]


def test_ai_language_and_fallback_are_isolated(client, monkeypatch):
    prompts = []
    monkeypatch.setattr(llm, "_CACHE", {})
    monkeypatch.setattr(llm, "_call_claude", lambda prompt: prompts.append(prompt))
    english = client.get("/api/explain/DE-101?lang=en").json()["analysis"]
    korean = client.get("/api/explain/DE-101?lang=ko").json()["analysis"]
    assert english["llm"] is False
    assert "Option" in english["recommendation"]
    assert english != korean
    assert "in English" in prompts[0]
    assert "한국어" in prompts[1]
    monkeypatch.setattr(chat, "llm_text", lambda prompt: prompts.append(prompt))
    reply = client.post("/api/chat?lang=en", json={"text": "Help"}).json()["reply"]
    assert reply.startswith("Unable")
    assert "in English" in prompts[-1]
    monkeypatch.setattr(commands, "_call_claude", lambda prompt: prompts.append(prompt))
    result = client.post("/api/command?lang=en", json={"text": "Add a bed"}).json()
    assert "AI request failed" in result["error"]
    assert "in English" in prompts[-1]
    assert LANGUAGE.get() == "ko"


def test_added_furniture_has_korean_name(demo_scene):
    commands._apply_op(demo_scene, {"op": "add_equipment", "type": "bed", "center": [2, 2]})
    assert demo_scene.equipment[-1].name == "침대 2"
