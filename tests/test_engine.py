"""Tests for the analysis engine."""

from unittest.mock import MagicMock
from app.analysis.engine import (
    analyze_match,
    get_match_summary,
    generate_recommendations,
    format_analysis_report,
    generate_weekly_summary,
    derive_lane_context,
)
from tests.conftest import SAMPLE_MATCH_DETAIL, SAMPLE_ANALYSIS


class TestGetMatchSummary:
    def test_successful_summary(self):
        watcher = MagicMock()
        watcher.match.by_id.return_value = SAMPLE_MATCH_DETAIL

        result = get_match_summary(watcher, "americas", "test-puuid-123", "NA1_123")

        assert result is not None
        assert result["match_id"] == "NA1_123"
        assert result["champion"] == "Ahri"
        assert result["win"] is True
        assert result["kills"] == 8
        assert result["deaths"] == 3
        assert result["assists"] == 12
        assert result["game_duration"] == 30.0
        assert result["queue_type"] == "Ranked Solo"

    def test_player_not_found(self):
        watcher = MagicMock()
        watcher.match.by_id.return_value = SAMPLE_MATCH_DETAIL

        result = get_match_summary(watcher, "americas", "nonexistent-puuid", "NA1_123")

        assert result is None

    def test_api_error_returns_none(self):
        from riotwatcher import ApiError

        watcher = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        watcher.match.by_id.side_effect = ApiError("error", mock_resp)

        result = get_match_summary(watcher, "americas", "test-puuid-123", "NA1_123")

        assert result is None

    def test_unknown_queue_id(self):
        match_data = {
            "info": {
                "gameDuration": 900,
                "queueId": 9999,
                "participants": [
                    {
                        "puuid": "test-puuid",
                        "championName": "Zed",
                        "kills": 5,
                        "deaths": 2,
                        "assists": 3,
                        "win": True,
                    },
                ],
            }
        }
        watcher = MagicMock()
        watcher.match.by_id.return_value = match_data

        result = get_match_summary(watcher, "americas", "test-puuid", "NA1_456")

        assert result is not None
        assert result["queue_type"] == "Other"

    def test_missing_queue_id(self):
        match_data = {
            "info": {
                "gameDuration": 600,
                "participants": [
                    {
                        "puuid": "test-puuid",
                        "championName": "Lux",
                        "kills": 1,
                        "deaths": 0,
                        "assists": 10,
                        "win": False,
                    },
                ],
            }
        }
        watcher = MagicMock()
        watcher.match.by_id.return_value = match_data

        result = get_match_summary(watcher, "americas", "test-puuid", "NA1_789")

        assert result is not None
        assert result["queue_type"] == "Other"
        assert result["game_duration"] == 10.0


class TestAnalyzeMatch:
    def test_successful_analysis(self):
        watcher = MagicMock()
        watcher.match.by_id.return_value = SAMPLE_MATCH_DETAIL

        result = analyze_match(watcher, "americas", "test-puuid-123", "NA1_123")

        assert result is not None
        assert result["champion"] == "Ahri"
        assert result["win"] is True
        assert result["kills"] == 8
        assert result["deaths"] == 3
        assert result["assists"] == 12
        assert result["kda"] == round((8 + 12) / 3, 2)
        assert result["gold_earned"] == 12500
        assert result["vision_score"] == 25
        assert result["cs_total"] == 200
        assert result["match_id"] == "NA1_123"
        assert result["gold_per_min"] > 0
        assert result["damage_per_min"] > 0
        assert isinstance(result["recommendations"], list)
        assert result["player_position"] == "MIDDLE"
        assert result["lane_opponent"] is not None
        assert result["lane_opponent"]["champion"] == "Syndra"
        assert "item_ids" in result
        assert "player_summoner_id" in result
        assert result["queue_id"] == 420

    def test_player_not_found_in_match(self):
        watcher = MagicMock()
        watcher.match.by_id.return_value = SAMPLE_MATCH_DETAIL

        result = analyze_match(watcher, "americas", "nonexistent-puuid", "NA1_123")

        assert result is None

    def test_api_error_returns_none(self):
        from riotwatcher import ApiError

        watcher = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        watcher.match.by_id.side_effect = ApiError("error", mock_resp)

        result = analyze_match(watcher, "americas", "test-puuid-123", "NA1_123")

        assert result is None

    def test_zero_deaths_no_division_error(self):
        match_data = {
            "info": {
                "gameDuration": 1200,
                "participants": [
                    {
                        "puuid": "zero-deaths",
                        "championName": "Janna",
                        "kills": 2,
                        "deaths": 0,
                        "assists": 20,
                        "goldEarned": 8000,
                        "totalDamageDealt": 30000,
                        "totalDamageDealtToChampions": 8000,
                        "visionScore": 50,
                        "totalMinionsKilled": 30,
                        "neutralMinionsKilled": 0,
                        "win": True,
                    },
                    *[
                        {
                            "puuid": f"p-{i}",
                            "championName": "Garen",
                            "kills": 3,
                            "deaths": 5,
                            "assists": 4,
                            "goldEarned": 9000,
                            "totalDamageDealt": 60000,
                            "totalDamageDealtToChampions": 18000,
                            "visionScore": 10,
                            "totalMinionsKilled": 120,
                            "neutralMinionsKilled": 0,
                            "win": True,
                        }
                        for i in range(9)
                    ],
                ],
            }
        }
        watcher = MagicMock()
        watcher.match.by_id.return_value = match_data

        result = analyze_match(watcher, "americas", "zero-deaths", "NA1_999")

        assert result is not None
        assert result["kda"] == 22.0  # (2+20)/max(1,0) = 22


    def test_analyze_returns_queue_type(self):
        watcher = MagicMock()
        watcher.match.by_id.return_value = SAMPLE_MATCH_DETAIL

        result = analyze_match(watcher, "americas", "test-puuid-123", "NA1_123")

        assert result["queue_type"] == "Ranked Solo"

    def test_analyze_returns_participants(self):
        watcher = MagicMock()
        watcher.match.by_id.return_value = SAMPLE_MATCH_DETAIL

        result = analyze_match(watcher, "americas", "test-puuid-123", "NA1_123")

        assert len(result["participants"]) == 10
        player_entries = [p for p in result["participants"] if p["is_player"]]
        assert len(player_entries) == 1
        assert player_entries[0]["champion"] == "Ahri"
        assert player_entries[0]["summoner_name"] == "TestPlayer"
        assert player_entries[0]["tagline"] == "NA1"
        assert player_entries[0]["team_id"] == 100
        assert "summoner_id" in player_entries[0]
        assert "item_ids" in player_entries[0]

        assert player_entries[0]["position"] == "MIDDLE"

        non_players = [p for p in result["participants"] if not p["is_player"]]
        assert len(non_players) == 9
        # Check enemies have positions
        enemies = [p for p in non_players if p["team_id"] == 200]
        assert all(p["position"] for p in enemies)

    def test_analyze_returns_game_start_timestamp(self):
        watcher = MagicMock()
        watcher.match.by_id.return_value = SAMPLE_MATCH_DETAIL

        result = analyze_match(watcher, "americas", "test-puuid-123", "NA1_123")

        assert result["game_start_timestamp"] == 1700000000000


class TestGenerateRecommendations:
    def test_low_kda_recommendation(self):
        player = {
            "kills": 1, "deaths": 8, "assists": 2,
            "visionScore": 20, "goldEarned": 8000, "totalDamageDealtToChampions": 50000,
        }
        match = {"info": {"participants": [
            {**player, "puuid": "p"},
            *[{"goldEarned": 10000, "totalDamageDealtToChampions": 50000, "puuid": f"t{i}"} for i in range(4)],
            *[{"goldEarned": 10000, "totalDamageDealtToChampions": 50000, "puuid": f"e{i}"} for i in range(5)],
        ]}}

        recs = generate_recommendations(player, match)

        assert any("survival" in r.lower() for r in recs)

    def test_high_kda_recommendation(self):
        player = {
            "kills": 15, "deaths": 2, "assists": 10,
            "visionScore": 30, "goldEarned": 15000, "totalDamageDealtToChampions": 100000,
        }
        match = {"info": {"participants": [
            {**player, "puuid": "p"},
            *[{"goldEarned": 10000, "totalDamageDealtToChampions": 50000, "puuid": f"t{i}"} for i in range(4)],
            *[{"goldEarned": 10000, "totalDamageDealtToChampions": 50000, "puuid": f"e{i}"} for i in range(5)],
        ]}}

        recs = generate_recommendations(player, match)

        assert any("great kda" in r.lower() for r in recs)

    def test_low_vision_recommendation(self):
        player = {
            "kills": 5, "deaths": 5, "assists": 5,
            "visionScore": 5, "goldEarned": 10000, "totalDamageDealtToChampions": 60000,
        }
        match = {"info": {"participants": [
            {**player, "puuid": "p"},
            *[{"goldEarned": 10000, "totalDamageDealtToChampions": 50000, "puuid": f"t{i}"} for i in range(4)],
            *[{"goldEarned": 10000, "totalDamageDealtToChampions": 50000, "puuid": f"e{i}"} for i in range(5)],
        ]}}

        recs = generate_recommendations(player, match)

        assert any("vision" in r.lower() for r in recs)

    def test_solid_performance_fallback(self):
        player = {
            "kills": 4, "deaths": 2, "assists": 4,
            "visionScore": 30, "goldEarned": 10000, "totalDamageDealtToChampions": 50000,
        }
        match = {"info": {"participants": [
            {**player, "puuid": "p"},
            *[{"goldEarned": 10000, "totalDamageDealtToChampions": 50000, "puuid": f"t{i}"} for i in range(4)],
            *[{"goldEarned": 10000, "totalDamageDealtToChampions": 50000, "puuid": f"e{i}"} for i in range(5)],
        ]}}

        recs = generate_recommendations(player, match)

        assert any("solid" in r.lower() for r in recs)


class TestFormatAnalysisReport:
    def test_win_report(self):
        report = format_analysis_report(SAMPLE_ANALYSIS)

        assert "WIN" in report
        assert "Ahri" in report
        assert "8/3/12" in report
        assert "Recommendations" in report

    def test_loss_report(self):
        analysis = {**SAMPLE_ANALYSIS, "win": False}
        report = format_analysis_report(analysis)

        assert "LOSS" in report


class TestGenerateWeeklySummary:
    def test_successful_summary(self):
        analyses = [
            {"win": True, "kda": 5.0, "gold_per_min": 400, "damage_per_min": 3000},
            {"win": False, "kda": 2.0, "gold_per_min": 300, "damage_per_min": 2000},
            {"win": True, "kda": 8.0, "gold_per_min": 500, "damage_per_min": 4000},
        ]

        result = generate_weekly_summary(analyses)

        assert result is not None
        assert result["total_games"] == 3
        assert result["wins"] == 2
        assert result["avg_kda"] == 5.0
        assert result["avg_gold_per_min"] == 400.0
        assert result["avg_damage_per_min"] == 3000.0
        assert "Weekly Summary" in result["summary_text"]
        assert "66.7%" in result["summary_text"]

    def test_empty_analyses_returns_none(self):
        assert generate_weekly_summary([]) is None

    def test_all_losses_includes_improvement_tip(self):
        analyses = [
            {"win": False, "kda": 1.5, "gold_per_min": 250, "damage_per_min": 1500},
            {"win": False, "kda": 1.0, "gold_per_min": 200, "damage_per_min": 1200},
        ]

        result = generate_weekly_summary(analyses)

        assert "Improvement Focus" in result["summary_text"]


class TestDeriveLaneContext:
    def test_finds_lane_opponent(self):
        participants = [
            {"is_player": True, "position": "MIDDLE", "team_id": 100, "champion": "Ahri"},
            {"is_player": False, "position": "MIDDLE", "team_id": 200, "champion": "Syndra"},
            {"is_player": False, "position": "TOP", "team_id": 200, "champion": "Darius"},
        ]
        pos, opponent = derive_lane_context(participants)
        assert pos == "MIDDLE"
        assert opponent is not None
        assert opponent["champion"] == "Syndra"

    def test_no_position_data(self):
        participants = [
            {"is_player": True, "position": "", "team_id": 100, "champion": "Ahri"},
            {"is_player": False, "position": "", "team_id": 200, "champion": "Syndra"},
        ]
        pos, opponent = derive_lane_context(participants)
        assert pos == ""
        assert opponent is None

    def test_missing_position_key(self):
        participants = [
            {"is_player": True, "team_id": 100, "champion": "Ahri"},
            {"is_player": False, "team_id": 200, "champion": "Syndra"},
        ]
        pos, opponent = derive_lane_context(participants)
        assert pos == ""
        assert opponent is None

    def test_empty_list(self):
        pos, opponent = derive_lane_context([])
        assert pos == ""
        assert opponent is None

    def test_no_matching_enemy_position(self):
        participants = [
            {"is_player": True, "position": "MIDDLE", "team_id": 100, "champion": "Ahri"},
            {"is_player": False, "position": "TOP", "team_id": 200, "champion": "Darius"},
        ]
        pos, opponent = derive_lane_context(participants)
        assert pos == "MIDDLE"
        assert opponent is None
