"""Cache/provider helper bridge for LLM modules."""

from app.analysis import llm_prompt as _prompt


def _is_opencode_zen_url(api_url: str) -> bool:
    return _prompt._is_opencode_zen_url(api_url)


def _is_prompt_tokens_500_error(api_url: str, status_code: int, response_text: str) -> bool:
    return _prompt._is_prompt_tokens_500_error(api_url, status_code, response_text)


def _resolve_provider_model(api_url: str, model: str):
    return _prompt._resolve_provider_model(api_url, model)
