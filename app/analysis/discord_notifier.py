"""Discord notification via REST API (no Gateway connection needed)."""

import logging
import requests
from flask import current_app
from app.analysis.rate_limit import throttle_discord_api

logger = logging.getLogger(__name__)

DISCORD_API_BASE = 'https://discord.com/api/v10'


def send_message(channel_id: str, content: str) -> bool:
    """Send a message to a Discord channel via REST API."""
    token = current_app.config['DISCORD_BOT_TOKEN']
    if not token:
        logger.warning("Discord bot token not configured, skipping notification")
        return False

    url = f'{DISCORD_API_BASE}/channels/{channel_id}/messages'
    headers = {
        'Authorization': f'Bot {token}',
        'Content-Type': 'application/json',
    }

    # Discord has a 2000 character limit per message
    if len(content) > 2000:
        content = content[:1997] + '...'

    try:
        throttle_discord_api('send_message')
        resp = requests.post(url, json={'content': content}, headers=headers, timeout=10)
        if resp.status_code in (200, 201):
            return True
        logger.error("Discord API error %d: %s", resp.status_code, resp.text)
        return False
    except requests.RequestException as e:
        logger.error("Failed to send Discord message: %s", e)
        return False


def get_bot_invite_url() -> str:
    """Generate the bot invite URL with required permissions."""
    client_id = current_app.config.get('DISCORD_CLIENT_ID', '')
    if not client_id:
        return ''
    # Permission 2048 = Send Messages
    return f'https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions=2048&scope=bot'
