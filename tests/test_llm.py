"""Tests for LLM integration."""

from unittest.mock import patch, MagicMock
from app.analysis.llm import get_llm_analysis, get_llm_analysis_detailed, iter_llm_analysis_stream
from tests.conftest import SAMPLE_ANALYSIS


class TestGetLlmAnalysis:
    @patch("app.analysis.llm_client.requests.post")
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

    @patch("app.analysis.llm_client.requests.post")
    def test_api_error_returns_none(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        with app.app_context():
            result = get_llm_analysis(SAMPLE_ANALYSIS)

        assert result is None

    @patch("app.analysis.llm_client.requests.post")
    def test_timeout_returns_none(self, mock_post, app):
        import requests
        mock_post.side_effect = requests.Timeout("Request timed out")

        with app.app_context():
            result = get_llm_analysis(SAMPLE_ANALYSIS)

        assert result is None

    @patch("app.analysis.llm_client.requests.post")
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

    @patch("app.analysis.llm_client.requests.post")
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
        assert "Knowledge Context" in user_message

    @patch("app.analysis.llm_client.requests.post")
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
        assert "Current Data Dragon patch" in user_message

    @patch("app.analysis.llm.requests.post")
    def test_prompt_includes_coach_mode_instruction(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Analysis"}}]
        }
        mock_post.return_value = mock_resp

        with app.app_context():
            get_llm_analysis({**SAMPLE_ANALYSIS, "coach_mode": "aggressive"})

        call_kwargs = mock_post.call_args
        system_message = call_kwargs[1]["json"]["messages"][0]["content"]
        user_message = call_kwargs[1]["json"]["messages"][1]["content"]
        assert "Coach mode: aggressive" in system_message
        assert "Coach Mode: aggressive" in user_message


class TestGetLlmAnalysisDetailed:
    @patch("app.analysis.llm_client.requests.post")
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

    @patch("app.analysis.llm_client.requests.post")
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

    @patch("app.analysis.llm_client.requests.post")
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

    @patch("app.analysis.llm_client.requests.post")
    def test_timeout_returns_error(self, mock_post, app):
        import requests
        mock_post.side_effect = requests.Timeout("timed out")

        with app.app_context():
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)

        assert result is None
        assert "timed out" in error.lower()

    @patch("app.analysis.llm_client.requests.post")
    def test_uses_configured_timeout_and_max_tokens(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Detailed analysis"}}]
        }
        mock_resp.text = '{"choices":[{"message":{"content":"Detailed analysis"}}]}'
        mock_post.return_value = mock_resp

        with app.app_context():
            app.config["LLM_TIMEOUT_SECONDS"] = 12
            app.config["LLM_MAX_TOKENS"] = 1234
            app.config["LLM_RETRIES"] = 0
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)

        assert error is None
        assert result == "Detailed analysis"
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["timeout"] == 12
        assert call_kwargs[1]["json"]["max_tokens"] == 1234

    @patch("app.analysis.llm_client.requests.post")
    def test_response_token_target_is_soft_guidance_not_hard_cap(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Detailed analysis"}}]
        }
        mock_resp.text = '{"choices":[{"message":{"content":"Detailed analysis"}}]}'
        mock_post.return_value = mock_resp

        with app.app_context():
            app.config["LLM_MAX_TOKENS"] = 1200
            app.config["LLM_RESPONSE_TOKEN_TARGET"] = 300
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)
            app.config["LLM_RESPONSE_TOKEN_TARGET"] = 0

        assert error is None
        assert result == "Detailed analysis"
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["max_tokens"] == 1200

    @patch("app.analysis.llm_client.time.sleep", return_value=None)
    @patch("app.analysis.llm_client.requests.post")
    def test_retries_once_after_timeout(self, mock_post, _mock_sleep, app):
        import requests
        timeout_error = requests.Timeout("timed out")
        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = {
            "choices": [{"message": {"content": "Recovered analysis"}}]
        }
        success_resp.text = '{"choices":[{"message":{"content":"Recovered analysis"}}]}'
        mock_post.side_effect = [timeout_error, success_resp]

        with app.app_context():
            app.config["LLM_TIMEOUT_SECONDS"] = 5
            app.config["LLM_RETRIES"] = 1
            app.config["LLM_RETRY_BACKOFF_SECONDS"] = 0
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)

        assert error is None
        assert result == "Recovered analysis"
        assert mock_post.call_count == 2

    @patch("app.analysis.llm_client.requests.post")
    @patch("app.analysis.llm_prompt.requests.get")
    def test_opencode_zen_deepseek_falls_back_to_glm(self, mock_get, mock_post, app):
        models_resp = MagicMock()
        models_resp.status_code = 200
        models_resp.json.return_value = {
            "data": [{"id": "glm-4.7-free"}, {"id": "big-pickle"}]
        }
        mock_get.return_value = models_resp

        completion_resp = MagicMock()
        completion_resp.status_code = 200
        completion_resp.json.return_value = {
            "choices": [{"message": {"content": "Fallback model response"}}]
        }
        completion_resp.text = '{"choices":[{"message":{"content":"Fallback model response"}}]}'
        mock_post.return_value = completion_resp

        with app.app_context():
            original_url = app.config["LLM_API_URL"]
            original_model = app.config["LLM_MODEL"]
            app.config["LLM_API_URL"] = "https://opencode.ai/zen/v1/chat/completions"
            app.config["LLM_MODEL"] = "deepseek-chat"
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)
            app.config["LLM_API_URL"] = original_url
            app.config["LLM_MODEL"] = original_model

        assert error is None
        assert result == "Fallback model response"
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["model"] == "glm-4.7-free"

    @patch("app.analysis.llm_client.requests.post")
    @patch("app.analysis.llm_prompt.requests.get")
    def test_opencode_zen_rejects_responses_model_on_chat_completions(self, mock_get, mock_post, app):
        models_resp = MagicMock()
        models_resp.status_code = 200
        models_resp.json.return_value = {
            "data": [{"id": "gpt-5.2"}, {"id": "glm-4.7-free"}]
        }
        mock_get.return_value = models_resp

        with app.app_context():
            original_url = app.config["LLM_API_URL"]
            original_model = app.config["LLM_MODEL"]
            app.config["LLM_API_URL"] = "https://opencode.ai/zen/v1/chat/completions"
            app.config["LLM_MODEL"] = "gpt-5.2"
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)
            app.config["LLM_API_URL"] = original_url
            app.config["LLM_MODEL"] = original_model

        assert result is None
        assert "not compatible with /chat/completions" in error
        mock_post.assert_not_called()

    def test_opencode_zen_non_chat_endpoint_returns_configuration_error(self, app):
        with app.app_context():
            original_url = app.config["LLM_API_URL"]
            original_model = app.config["LLM_MODEL"]
            app.config["LLM_API_URL"] = "https://opencode.ai/zen/v1/responses"
            app.config["LLM_MODEL"] = "gpt-5.2"
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)
            app.config["LLM_API_URL"] = original_url
            app.config["LLM_MODEL"] = original_model

        assert result is None
        assert "set llm_api_url to https://opencode.ai/zen/v1/chat/completions" in error.lower()

    @patch("app.analysis.llm_client.requests.post")
    @patch("app.analysis.llm_prompt.requests.get")
    def test_opencode_prompt_tokens_500_retries_without_temperature(self, mock_get, mock_post, app):
        models_resp = MagicMock()
        models_resp.status_code = 200
        models_resp.json.return_value = {
            "data": [{"id": "big-pickle"}, {"id": "glm-4.7-free"}]
        }
        mock_get.return_value = models_resp

        crash_resp = MagicMock()
        crash_resp.status_code = 500
        crash_resp.text = '{"type":"error","error":{"message":"Cannot read properties of undefined (reading \\"prompt_tokens\\")"}}'

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = {
            "choices": [{"message": {"content": "Recovered after temperature removal"}}]
        }
        success_resp.text = '{"choices":[{"message":{"content":"Recovered after temperature removal"}}]}'
        mock_post.side_effect = [crash_resp, success_resp]

        with app.app_context():
            original_url = app.config["LLM_API_URL"]
            original_model = app.config["LLM_MODEL"]
            app.config["LLM_API_URL"] = "https://opencode.ai/zen/v1/chat/completions"
            app.config["LLM_MODEL"] = "big-pickle"
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)
            app.config["LLM_API_URL"] = original_url
            app.config["LLM_MODEL"] = original_model

        assert error is None
        assert result == "Recovered after temperature removal"
        assert mock_post.call_count == 2
        first_json = mock_post.call_args_list[0][1]["json"]
        second_json = mock_post.call_args_list[1][1]["json"]
        assert first_json["model"] == "big-pickle"
        assert "temperature" in first_json
        assert second_json["model"] == "big-pickle"
        assert "temperature" not in second_json

    @patch("app.analysis.llm_client.requests.post")
    @patch("app.analysis.llm_prompt.requests.get")
    def test_opencode_prompt_tokens_500_falls_back_to_default_model(self, mock_get, mock_post, app):
        models_resp = MagicMock()
        models_resp.status_code = 200
        models_resp.json.return_value = {
            "data": [{"id": "big-pickle"}, {"id": "glm-4.7-free"}]
        }
        mock_get.return_value = models_resp

        crash_resp = MagicMock()
        crash_resp.status_code = 500
        crash_resp.text = '{"type":"error","error":{"message":"Cannot read properties of undefined (reading \\"prompt_tokens\\")"}}'

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = {
            "choices": [{"message": {"content": "Recovered with model fallback"}}]
        }
        success_resp.text = '{"choices":[{"message":{"content":"Recovered with model fallback"}}]}'
        mock_post.side_effect = [crash_resp, crash_resp, crash_resp, success_resp]

        with app.app_context():
            original_url = app.config["LLM_API_URL"]
            original_model = app.config["LLM_MODEL"]
            app.config["LLM_API_URL"] = "https://opencode.ai/zen/v1/chat/completions"
            app.config["LLM_MODEL"] = "big-pickle"
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)
            app.config["LLM_API_URL"] = original_url
            app.config["LLM_MODEL"] = original_model

        assert error is None
        assert result == "Recovered with model fallback"
        assert mock_post.call_count == 4
        third_json = mock_post.call_args_list[2][1]["json"]
        fourth_json = mock_post.call_args_list[3][1]["json"]
        assert third_json["model"] == "big-pickle"
        assert "temperature" not in third_json
        assert "max_tokens" not in third_json
        assert fourth_json["model"] == "glm-4.7-free"
        assert "temperature" not in fourth_json
        assert "max_tokens" not in fourth_json

    @patch("app.analysis.llm_client.requests.post")
    def test_prompt_includes_length_budget_instruction_when_configured(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Detailed analysis"}}]
        }
        mock_resp.text = '{"choices":[{"message":{"content":"Detailed analysis"}}]}'
        mock_post.return_value = mock_resp

        with app.app_context():
            app.config["LLM_RESPONSE_TOKEN_TARGET"] = 280
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)
            app.config["LLM_RESPONSE_TOKEN_TARGET"] = 0

        assert error is None
        assert result == "Detailed analysis"
        user_prompt = mock_post.call_args[1]["json"]["messages"][1]["content"]
        assert "Target length: about 280 tokens" in user_prompt
        assert "Use concise Markdown" in user_prompt
        assert "## Summary" in user_prompt
        assert "## 2 Drills" in user_prompt

    @patch("app.analysis.llm.requests.post")
    def test_prompt_enforces_structured_coaching_brief_schema(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Detailed analysis"}}]
        }
        mock_resp.text = '{"choices":[{"message":{"content":"Detailed analysis"}}]}'
        mock_post.return_value = mock_resp

        with app.app_context():
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)

        assert error is None
        assert result == "Detailed analysis"
        user_prompt = mock_post.call_args[1]["json"]["messages"][1]["content"]
        assert "## Summary" in user_prompt
        assert "## Top 3 Issues" in user_prompt
        assert "## Evidence" in user_prompt
        assert "## Next-Game Mission" in user_prompt
        assert "## 2 Drills" in user_prompt
        assert "In [situation Y], do [action X], and measure success with [observable criterion]." in user_prompt
        assert "## Match Snapshot" not in user_prompt
        assert "## Why This Game Happened" not in user_prompt
        assert "## Action Plan (Next 3 Games)" not in user_prompt
        ordered_sections = [
            "## Summary",
            "## Top 3 Issues",
            "## Evidence",
            "## Next-Game Mission",
            "## 2 Drills",
        ]
        indices = [user_prompt.index(section) for section in ordered_sections]
        assert indices == sorted(indices)

    @patch("app.analysis.llm.requests.post")
    def test_response_text_is_normalized_from_markdownish_content(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "# Overall\n- **Good** lane control\n1. `Practice` wave timing"}}]
        }
        mock_resp.text = '{"choices":[{"message":{"content":"# Overall\\n- **Good** lane control\\n1. `Practice` wave timing"}}]}'
        mock_post.return_value = mock_resp

        with app.app_context():
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS)

        assert error is None
        assert result == "# Overall\n- **Good** lane control\n1. `Practice` wave timing"

    @patch("app.analysis.llm_client.requests.post")
    def test_chinese_language_prompt_scaffold(self, mock_post, app):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "中文分析"}}]
        }
        mock_resp.text = '{"choices":[{"message":{"content":"中文分析"}}]}'
        mock_post.return_value = mock_resp

        with app.app_context():
            result, error = get_llm_analysis_detailed(SAMPLE_ANALYSIS, language="zh-CN")

        assert error is None
        assert result == "中文分析"
        user_prompt = mock_post.call_args[1]["json"]["messages"][1]["content"]
        assert "对局数据" in user_prompt
        assert "Markdown" in user_prompt
        assert "## 总结" in user_prompt
        assert "## 3个首要问题" in user_prompt
        assert "## 证据" in user_prompt
        assert "## 下一局任务" in user_prompt
        assert "## 2个训练" in user_prompt
        assert "## 对局快照" not in user_prompt
        assert "## 对局成因" not in user_prompt
        assert "## 三局行动计划" not in user_prompt


class TestIterLlmAnalysisStream:
    @patch("app.analysis.llm_client.requests.post")
    def test_stream_yields_chunks_and_done(self, mock_post, app):
        stream_resp = MagicMock()
        stream_resp.status_code = 200
        stream_resp.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"content":"Great lane control. "}}]}',
            'data: {"choices":[{"delta":{"content":"Keep wave tempo."}}]}',
            'data: [DONE]',
        ]
        mock_post.return_value = stream_resp

        with app.app_context():
            events = list(iter_llm_analysis_stream(SAMPLE_ANALYSIS))

        assert events[0]["type"] == "chunk"
        assert events[0]["delta"] == "Great lane control. "
        assert events[1]["type"] == "chunk"
        assert events[1]["delta"] == "Keep wave tempo."
        assert events[-1]["type"] == "done"
        assert events[-1]["analysis"] == "Great lane control. Keep wave tempo."

    @patch("app.analysis.llm_client.requests.post")
    def test_stream_timeout_returns_structured_error(self, mock_post, app):
        import requests
        mock_post.side_effect = requests.Timeout("timed out")

        with app.app_context():
            events = list(iter_llm_analysis_stream(SAMPLE_ANALYSIS))

        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "timed out" in events[0]["error"].lower()

    @patch("app.analysis.llm_client.requests.post")
    def test_stream_ignores_non_json_lines(self, mock_post, app):
        stream_resp = MagicMock()
        stream_resp.status_code = 200
        stream_resp.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"content":"# Header\\n"}}]}',
            'not-json',
            'data: {"choices":[{"delta":{"content":"- **Tip** text"}}]}',
            'data: [DONE]',
        ]
        mock_post.return_value = stream_resp

        with app.app_context():
            events = list(iter_llm_analysis_stream(SAMPLE_ANALYSIS))

        assert [e["type"] for e in events] == ["chunk", "chunk", "done"]
        assert events[-1]["analysis"] == "# Header\n- **Tip** text"
