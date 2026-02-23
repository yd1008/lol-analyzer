from app.dashboard import routes as dashboard_routes
from app.models import MatchAnalysis


def test_ai_coach_plan_focus_area_uses_actionable_death_plan(monkeypatch):
    """Low-KDA matches should emit an actionable death-focused recommendation."""

    monkeypatch.setattr(dashboard_routes, "lt", lambda en, zh: en)

    matches = [
        MatchAnalysis(
            win=False,
            kda=2.1,
            damage_per_min=600,
            gold_per_min=300,
            vision_score=10,
            match_id="NA1_low_sample",
        )
    ]

    plan = dashboard_routes._build_ai_coach_plan(matches)
    focus_lines = " ".join(plan["focus_areas"])

    assert "deaths at 4 or fewer per game" in focus_lines
    assert "safer" not in focus_lines.lower()
    assert any("Reduce avoidable deaths" in line for line in plan["focus_areas"])


def test_ai_coach_plan_returns_no_plan_when_empty(monkeypatch):
    """Empty match history should return a deterministic onboarding coaching plan."""

    monkeypatch.setattr(dashboard_routes, "lt", lambda en, zh: en)

    plan = dashboard_routes._build_ai_coach_plan([])

    assert plan["coach_score"] == 0
    assert plan["strengths"] == []
    assert plan["focus_areas"] == []
    assert "unlock" in plan["next_game_goal"]
