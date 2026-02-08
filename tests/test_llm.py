"""Tests for LLM integration."""

from unittest.mock import patch, MagicMock
from app.analysis.llm import get_llm_analysis, get_llm_analysis_detailed
from tests.conftest import SAMPLE_ANALYSIS


class TestGetLlmAnalysis:
    @patch("app.analysis.llm.requests.post")
    def test_successful_analysis(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {"message": {"content": "Great game on Ahri! Your KDA was excellent."}}
            ]
        }
        mock_post.return_value = mock_resp

        with app.app_context():
            result = get_llm_analysis(SAMPLE_ANALYSIS)

        assert result == "Great game on Ahri! Your KDA was excellent."
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["model"] == "test-model"
        assert len(call_kwargs[1]["json"]["messages"]) == 2

    @patch("app.analysis.llm.requests.post")
    def test_api_error_returns_none(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        with app.app_context():
            result = get_llm_analysis(SAMPLE_ANALYSIS)

        assert result is None

    @patch("app.analysis.llm.requests.post")
    def test_timeout_returns_none(self, mock_post, app):
        import requests
        mock_post.side_effect = requests.Timeout("Request timed out")

        with app.app_context():
            result = get_llm_analysis(SAMPLE_ANALYSIS)

        assert result is None

    @patch("app.analysis.llm.requests.post")
    def test_malformed_response_returns_none(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"unexpected": "format"}
        mock_resp.text = '{"unexpected": "format"}'
        mock_post.return_value = mock_resp

        with app.app_context():
            result = get_llm_analysis(SAMPLE_ANALYSIS)

        assert result is None

    def test_no_api_key_returns_none(self, app):
        with app.app_context():
            app.config["LLM_API_KEY"] = ""
            result = get_llm_analysis(SAMPLE_ANALYSIS)
            app.config["LLM_API_KEY"] = "test-llm-key"

        assert result is None

    def test_no_api_url_returns_none(self, app):
        with app.app_context():
            app.config["LLM_API_URL"] = ""
            result = get_llm_analysis(SAMPLE_ANALYSIS)
            app.config["LLM_API_URL"] = "https://api.example.com/v1/chat/completions"

        assert result is None

    @patch("app.analysis.llm.requests.post")
    def test_prompt_includes_match_data(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Analysis"}}]
        }
        mock_post.return_value = mock_resp

        with app.app_context():
            get_llm_analysis(SAMPLE_ANALYSIS)

        call_kwargs = mock_post.call_args
        user_message = call_kwargs[1]["json"]["messages"][1]["content"]
        assert "Ahri" in user_message
        assert "8/3/12" in user_message
        assert "Victory" in user_message

    @patch("app.analysis.llm.requests.post")
    def test_loss_result_in_prompt(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Analysis"}}]
        }
        mock_post.return_value = mock_resp

        loss_analysis = {**SAMPLE_ANALYSIS, "win": False}
        with app.app_context():
            get_llm_analysis(loss_analysis)

        call_kwargs = mock_post.call_args
        user_message = call_kwargs[1]["json"]["messages"][1]["content"]
        assert "Defeat" in user_message


class TestGetLlmAnalysisDetailed:
    @patch("app.analysis.llm.requests.post")
    def test_success_returns_text_and_no_error(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Detailed analysis"}}]
        }
        mock_post.return_value = mock_resp

        with app.app_context():
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)

        assert result == "Detailed analysis"
        assert error is None

    def test_missing_key_returns_error(self, app):
        with app.app_context():
            app.config["LLM_API_KEY"] = ""
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)
            app.config["LLM_API_KEY"] = "test-llm-key"

        assert result is None
        assert "LLM_API_KEY" in error

    def test_missing_url_returns_error(self, app):
        with app.app_context():
            app.config["LLM_API_URL"] = ""
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)
            app.config["LLM_API_URL"] = "https://api.example.com/v1/chat/completions"

        assert result is None
        assert "LLM_API_URL" in error

    @patch("app.analysis.llm.requests.post")
    def test_401_returns_auth_error(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_post.return_value = mock_resp

        with app.app_context():
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)

        assert result is None
        assert "401" in error
        assert "Authentication" in error

    @patch("app.analysis.llm.requests.post")
    def test_404_returns_url_error(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        mock_post.return_value = mock_resp

        with app.app_context():
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)

        assert result is None
        assert "404" in error
        assert "LLM_API_URL" in error

    @patch("app.analysis.llm.requests.post")
    def test_timeout_returns_error(self, mock_post, app):
        import requests
        mock_post.side_effect = requests.Timeout("timed out")

        with app.app_context():
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)

        assert result is None
        assert "timed out" in error.lower()
