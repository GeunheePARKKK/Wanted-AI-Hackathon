import pytest

from backend.detector import inspect_scene, violation_penalty


@pytest.mark.parametrize("severity,shortfall,expected", [
    ("HIGH", 0, 10), ("HIGH", 50, 11), ("HIGH", 500, 20),
    ("HIGH", 5000, 20), ("MEDIUM", 50, 5), ("MEDIUM", 300, 10),
    ("MEDIUM", 5000, 10), ("MEDIUM", -10, 4), ("HIGH", 12, 10.2),
])
def test_penalty_limits_and_gradient(severity, shortfall, expected):
    assert violation_penalty(severity, shortfall) == expected


def test_demo_penalties_match_geometry(demo_scene):
    result = inspect_scene(demo_scene)
    for v in result["violations"]:
        assert v["shortfall_mm"] == max(v["required_mm"] - v["measured_mm"], 0)
        assert v["penalty"] == violation_penalty(v["severity"], v["shortfall_mm"])
    assert result["summary"]["score"] == max(0, 100 - sum(v["penalty"] for v in result["violations"]))
