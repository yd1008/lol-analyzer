"""LLM-powered match analysis using OpenCode Zen API (OpenAI-compatible)."""

import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)


def _build_prompt(analysis: dict) -> tuple[str, str]:
    """Build the system and user prompts for LLM analysis."""
    result_str = "Victory" if analysis['win'] else "Defeat"
    system = "You are a concise, expert League of Legends performance coach. Give specific, data-driven advice."
    user = (
        "You are an expert League of Legends coach. Analyze this match performance "
        "and provide specific, actionable coaching advice.\n\n"
        "Match Data:\n"
        f"- Champion: {analysis['champion']}\n"
        f"- Result: {result_str}\n"
        f"- KDA: {analysis['kills']}/{analysis['deaths']}/{analysis['assists']} (Ratio: {analysis['kda']})\n"
        f"- Gold: {analysis['gold_earned']} total ({analysis['gold_per_min']}/min)\n"
        f"- Damage: {analysis['total_damage']} total ({analysis['damage_per_min']}/min)\n"
        f"- Vision Score: {analysis['vision_score']}\n"
        f"- CS: {analysis['cs_total']}\n"
        f"- Game Duration: {analysis['game_duration']} minutes\n\n"
        "Provide a concise analysis (3-5 paragraphs) covering:\n"
        "1. Overall performance assessment for this champion\n"
        "2. Key strengths shown in this match\n"
        "3. Specific areas to improve with actionable advice\n"
        "4. One concrete thing to practice in the next game\n\n"
        "Keep it direct and specific to this match data. No generic advice."
    )
    return system, user


def get_llm_analysis(analysis: dict) -> str | None:
    """Generate deep AI analysis for a match using the LLM API.

    Uses the OpenCode Zen API (OpenAI-compatible chat completions endpoint).
    Returns the analysis text on success, None on failure.
    Errors are logged but not surfaced. Use get_llm_analysis_detailed
    for admin/debug use cases that need error details.
    """
    result, error = get_llm_analysis_detailed(analysis)
    if error:
        logger.error("LLM analysis failed: %s", error)
    return result


def get_llm_analysis_detailed(analysis: dict) -> tuple[str | None, str | None]:
    """Generate LLM analysis and return (result, error_message).

    On success: (analysis_text, None)
    On failure: (None, error_description)
    """
    api_key = current_app.config.get('LLM_API_KEY', '')
    api_url = current_app.config.get('LLM_API_URL', '')
    model = current_app.config.get('LLM_MODEL', 'deepseek-chat')

    if not api_key:
        return None, "LLM_API_KEY is not set."
    if not api_url:
        return None, "LLM_API_URL is not set."

    system_prompt, user_prompt = _build_prompt(analysis)

    try:
        resp = requests.post(
            api_url,
            json={
                'model': model,
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                'max_tokens': 1500,
                'temperature': 0.7,
            },
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            timeout=90,
        )

        if resp.status_code == 401:
            return None, f"Authentication failed (401). Check your LLM_API_KEY. Response: {resp.text[:200]}"
        if resp.status_code == 404:
            return None, f"Endpoint not found (404). Check your LLM_API_URL: {api_url}"
        if resp.status_code != 200:
            return None, f"LLM API returned status {resp.status_code}: {resp.text[:300]}"

        raw_body = resp.text
        if not raw_body or not raw_body.strip():
            return None, f"LLM API returned empty response body. URL: {api_url} | Model: {model}"

        try:
            data = resp.json()
        except ValueError:
            return None, f"LLM API returned non-JSON response. URL: {api_url} | Body: {raw_body[:300]}"

        message = data.get('choices', [{}])[0].get('message', {})
        content = message.get('content') or message.get('reasoning_content') or ''
        if not content:
            return None, f"LLM API response missing choices/content. URL: {api_url} | Body: {raw_body[:300]}"

        return content.strip(), None

    except requests.Timeout:
        return None, f"Request timed out after 90s. URL: {api_url}"
    except requests.RequestException as e:
        return None, f"Request failed. URL: {api_url} | Error: {e}"
