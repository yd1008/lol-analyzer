from unittest.mock import patch

from app.analysis.discord_notifier import get_bot_invite_url, send_message


def test_get_bot_invite_url_without_client_id_returns_empty(app):
    with app.app_context():
        with patch('app.analysis.discord_notifier.current_app.config', {"DISCORD_CLIENT_ID": ""}):
            assert get_bot_invite_url() == ""


def test_send_message_skips_when_token_missing(app):
    with app.app_context():
        app.config['DISCORD_BOT_TOKEN'] = ""
        with patch('app.analysis.discord_notifier.requests.post') as post_mock:
            sent = send_message("123456789012345678", "hello")

    assert sent is False
    post_mock.assert_not_called()


def test_send_message_posts_and_truncates_when_needed(app):
    with app.app_context():
        app.config['DISCORD_BOT_TOKEN'] = "test-token"
        response = type("Resp", (), {"status_code": 201, "text": ""})()
        with patch('app.analysis.discord_notifier.requests.post', return_value=response) as post_mock, \
                patch('app.analysis.discord_notifier.throttle_discord_api') as throttle_mock:
            sent = send_message("123456789012345678", "x" * 2005)

    assert sent is True
    throttle_mock.assert_called_once_with("send_message")
    assert post_mock.call_count == 1
    args, kwargs = post_mock.call_args
    assert args[0].endswith('/channels/123456789012345678/messages')
    assert kwargs['headers']['Authorization'] == 'Bot test-token'
    assert kwargs['json']['content'].endswith('...')
    assert len(kwargs['json']['content']) == 2000
    assert kwargs['timeout'] == 10
