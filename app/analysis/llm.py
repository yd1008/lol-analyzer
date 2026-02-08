"""LLM-powered match analysis using OpenCode Zen API (OpenAI-compatible)."""

import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)


def get_llm_analysis(analysis: dict) -> str | None:
    """Generate deep AI analysis for a match using the LLM API.

    Uses the OpenCode Zen API (OpenAI-compatible chat completions endpoint).
    """
    api_key = current_app.config.get('LLM_API_KEY', '')
    api_url = current_app.config.get('LLM_API_URL', '')
    model = current_app.config.get('LLM_MODEL', 'deepseek-chat')

    if not api_key or not api_url:
        logger.debug("LLM not configured, skipping AI analysis")
        return None

    result_str = "Victory" if analysis['win'] else "Defeat"

    prompt = f"""You are an expert League of Legends coach. Analyze this match performance and provide specific, actionable coaching advice.

Match Data:
- Champion: {analysis['champion']}
- Result: {result_str}
- KDA: {analysis['kills']}/{analysis['deaths']}/{analysis['assists']} (Ratio: {analysis['kda']})
- Gold: {analysis['gold_earned']} total ({analysis['gold_per_min']}/min)
- Damage: {analysis['total_damage']} total ({analysis['damage_per_min']}/min)
- Vision Score: {analysis['vision_score']}
- CS: {analysis['cs_total']}
- Game Duration: {analysis['game_duration']} minutes

Provide a concise analysis (3-5 paragraphs) covering:
1. Overall performance assessment for this champion
2. Key strengths shown in this match
3. Specific areas to improve with actionable advice
4. One concrete thing to practice in the next game

Keep it direct and specific to this match data. No generic advice."""

    try:
        resp = requests.post(
            api_url,
            json={
                'model': model,
                'messages': [
                    {'role': 'system', 'content': 'You are a concise, expert League of Legends performance coach. Give specific, data-driven advice.'},
                    {'role': 'user', 'content': prompt},
                ],
                'max_tokens': 600,
                'temperature': 0.7,
            },
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            timeout=30,
        )

        if resp.status_code != 200:
            logger.error("LLM API error %d: %s", resp.status_code, resp.text[:200])
            return None

        data = resp.json()
        content = data['choices'][0]['message']['content']
        return content.strip()

    except requests.Timeout:
        logger.error("LLM API request timed out")
        return None
    except (KeyError, IndexError) as e:
        logger.error("Unexpected LLM API response format: %s", e)
        return None
    except requests.RequestException as e:
        logger.error("LLM API request failed: %s", e)
        return None
