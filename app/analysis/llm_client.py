"""LLM transport/client functions separated from prompt construction."""

from __future__ import annotations

import json
import logging
import time

import requests

from app.analysis.llm_cache import _is_prompt_tokens_500_error
from app.analysis.llm_prompt import (
    _build_base_request_body,
    _build_prompt,
    _extract_stream_delta,
    _llm_request_settings,
    _request_body_variants,
    _soft_text_clean,
)

logger = logging.getLogger(__name__)


def iter_llm_analysis_stream(analysis: dict, language: str = 'en'):
    """Yield stream events: chunk/done/error for OpenAI-compatible chat-completions stream."""
    settings, settings_error = _llm_request_settings()
    if settings_error:
        yield {'type': 'error', 'error': settings_error}
        return

    api_url = settings['api_url']
    model = settings['model']
    timeout_seconds = settings['timeout_seconds']
    retries = settings['retries']
    retry_backoff = settings['retry_backoff']
    headers = settings['headers']

    system_prompt, user_prompt = _build_prompt(analysis, language=language)
    base_body = _build_base_request_body(system_prompt, user_prompt, model, settings['max_tokens'])
    body_variants = _request_body_variants(api_url, base_body)

    last_error = ''
    attempts = retries + 1
    for variant_index, body in enumerate(body_variants):
        variant_model = body.get('model', model)
        stream_body = dict(body)
        stream_body['stream'] = True
        for attempt in range(attempts):
            resp = None
            try:
                resp = requests.post(
                    api_url,
                    json=stream_body,
                    headers=headers,
                    timeout=timeout_seconds,
                    stream=True,
                )
                if resp.status_code == 401:
                    yield {'type': 'error', 'error': f"Authentication failed (401). Check your LLM_API_KEY. Response: {resp.text[:200]}"}
                    return
                if resp.status_code == 404:
                    yield {'type': 'error', 'error': f"Endpoint not found (404). Check your LLM_API_URL: {api_url}"}
                    return
                if resp.status_code >= 500:
                    last_error = f"LLM API returned status {resp.status_code}: {resp.text[:300]}"
                    if _is_prompt_tokens_500_error(api_url, resp.status_code, resp.text) and variant_index < (len(body_variants) - 1):
                        logger.warning(
                            "OpenCode stream returned prompt_tokens 500 for model '%s'. Trying fallback payload variant %d/%d.",
                            variant_model,
                            variant_index + 2,
                            len(body_variants),
                        )
                        break
                    if attempt < retries:
                        if retry_backoff > 0:
                            time.sleep(retry_backoff * (2 ** attempt))
                        continue
                    yield {'type': 'error', 'error': last_error}
                    return
                if resp.status_code != 200:
                    yield {'type': 'error', 'error': f"LLM API returned status {resp.status_code}: {resp.text[:300]}"}
                    return

                collected = []
                for raw_line in resp.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    line = raw_line.strip()
                    if not line or line.startswith(':'):
                        continue
                    if line.startswith('data:'):
                        line = line[5:].strip()
                    if not line:
                        continue
                    if line == '[DONE]':
                        break
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    choices = payload.get('choices') or []
                    if not choices:
                        continue
                    delta_text = _extract_stream_delta(choices[0] or {})
                    if delta_text:
                        collected.append(delta_text)
                        yield {'type': 'chunk', 'delta': delta_text}

                content = _soft_text_clean(''.join(collected))
                if not content:
                    yield {'type': 'error', 'error': f"LLM stream response missing choices/content. URL: {api_url} | Model: {variant_model}"}
                    return
                yield {'type': 'done', 'analysis': content}
                return
            except requests.Timeout:
                last_error = (
                    f"Request timed out after {timeout_seconds}s (attempt {attempt + 1}/{attempts}). "
                    f"URL: {api_url} | Model: {variant_model}"
                )
                if attempt < retries:
                    if retry_backoff > 0:
                        time.sleep(retry_backoff * (2 ** attempt))
                    continue
                yield {
                    'type': 'error',
                    'error': (
                        f"{last_error} Consider lowering LLM_MAX_TOKENS/LLM_RESPONSE_TOKEN_TARGET "
                        "or verifying provider latency/endpoint."
                    ),
                }
                return
            except requests.RequestException as e:
                last_error = f"Request failed. URL: {api_url} | Error: {e}"
                if attempt < retries:
                    if retry_backoff > 0:
                        time.sleep(retry_backoff * (2 ** attempt))
                    continue
                yield {'type': 'error', 'error': last_error}
                return
            finally:
                if resp is not None:
                    resp.close()

    yield {'type': 'error', 'error': last_error or 'Unknown LLM stream request failure.'}


def get_llm_analysis(analysis: dict, language: str = 'en') -> str | None:
    """Generate deep AI analysis for a match using the LLM API."""
    result, error = get_llm_analysis_detailed(analysis, language=language)
    if error:
        logger.error('LLM analysis failed: %s', error)
    return result


def get_llm_analysis_detailed(analysis: dict, language: str = 'en') -> tuple[str | None, str | None]:
    """Generate LLM analysis and return (result, error_message)."""
    settings, settings_error = _llm_request_settings()
    if settings_error:
        return None, settings_error

    api_url = settings['api_url']
    model = settings['model']
    timeout_seconds = settings['timeout_seconds']
    retries = settings['retries']
    retry_backoff = settings['retry_backoff']
    headers = settings['headers']

    system_prompt, user_prompt = _build_prompt(analysis, language=language)
    base_body = _build_base_request_body(system_prompt, user_prompt, model, settings['max_tokens'])

    last_error = ''
    attempts = retries + 1
    body_variants = _request_body_variants(api_url, base_body)
    for variant_index, body in enumerate(body_variants):
        variant_model = body.get('model', model)
        for attempt in range(attempts):
            try:
                resp = requests.post(
                    api_url,
                    json=body,
                    headers=headers,
                    timeout=timeout_seconds,
                )
                if resp.status_code == 401:
                    return None, f"Authentication failed (401). Check your LLM_API_KEY. Response: {resp.text[:200]}"
                if resp.status_code == 404:
                    return None, f"Endpoint not found (404). Check your LLM_API_URL: {api_url}"
                if resp.status_code >= 500:
                    last_error = f"LLM API returned status {resp.status_code}: {resp.text[:300]}"
                    if _is_prompt_tokens_500_error(api_url, resp.status_code, resp.text) and variant_index < (len(body_variants) - 1):
                        logger.warning(
                            "OpenCode returned prompt_tokens 500 for model '%s'. Trying fallback payload variant %d/%d.",
                            variant_model,
                            variant_index + 2,
                            len(body_variants),
                        )
                        break
                    if attempt < retries:
                        if retry_backoff > 0:
                            time.sleep(retry_backoff * (2 ** attempt))
                        continue
                    return None, last_error
                if resp.status_code != 200:
                    return None, f"LLM API returned status {resp.status_code}: {resp.text[:300]}"

                raw_body = resp.text
                if not raw_body or not raw_body.strip():
                    return None, f"LLM API returned empty response body. URL: {api_url} | Model: {variant_model}"
                try:
                    data = resp.json()
                except ValueError:
                    return None, f"LLM API returned non-JSON response. URL: {api_url} | Body: {raw_body[:300]}"
                message = data.get('choices', [{}])[0].get('message', {})
                content = message.get('content') or message.get('reasoning_content') or ''
                if not content:
                    return None, f"LLM API response missing choices/content. URL: {api_url} | Body: {raw_body[:300]}"
                return _soft_text_clean(content), None
            except requests.Timeout:
                last_error = (
                    f"Request timed out after {timeout_seconds}s (attempt {attempt + 1}/{attempts}). "
                    f"URL: {api_url} | Model: {variant_model}"
                )
                if attempt < retries:
                    if retry_backoff > 0:
                        time.sleep(retry_backoff * (2 ** attempt))
                    continue
                return None, (
                    f"{last_error} Consider lowering LLM_MAX_TOKENS/LLM_RESPONSE_TOKEN_TARGET "
                    "or verifying provider latency/endpoint."
                )
            except requests.RequestException as e:
                last_error = f"Request failed. URL: {api_url} | Error: {e}"
                if attempt < retries:
                    if retry_backoff > 0:
                        time.sleep(retry_backoff * (2 ** attempt))
                    continue
                return None, last_error

    return None, last_error or 'Unknown LLM request failure.'
