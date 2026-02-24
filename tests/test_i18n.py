"""Tests for locale resolution and bilingual rendering behavior."""

import time
from unittest.mock import patch

import app.i18n as i18n
from app.i18n import champion_name, item_name, js_i18n_payload, queue_label, rank_tier_label


def test_locale_defaults_to_zh_without_cookie(app, db):
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "\u5de5\u4f5c\u6d41\u7a0b" in body


def test_locale_uses_en_cookie(app, db):
    client = app.test_client()
    client.set_cookie("lanescope-lang", "en", domain="localhost")
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "How It Works" in body


def test_invalid_cookie_falls_back_to_zh(app, db):
    client = app.test_client()
    client.set_cookie("lanescope-lang", "unknown-locale", domain="localhost")
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "\u5de5\u4f5c\u6d41\u7a0b" in body


def test_zh_queue_labels_use_game_terms():
    assert queue_label("Ranked Solo", locale="zh-CN") == "\u5355/\u53cc\u6392\u4f4d"
    assert queue_label("Normal Draft", locale="zh-CN") == "\u53ec\u5524\u5e08\u5ce1\u8c37\uff08\u5f81\u53ec\u6a21\u5f0f\uff09"


def test_zh_rank_tiers_use_official_names():
    assert rank_tier_label("CHALLENGER", locale="zh-CN") == "\u6700\u5f3a\u738b\u8005"
    assert rank_tier_label("DIAMOND", locale="zh-CN") == "\u7480\u74a8\u94bb\u77f3"


def test_zh_name_lookups_do_not_block_on_http_cache_miss():
    with i18n._LOCK:
        old_version = dict(i18n._VERSION_CACHE)
        old_champ = dict(i18n._CHAMPION_NAME_CACHE)
        old_item = dict(i18n._ITEM_NAME_CACHE)
        i18n._VERSION_CACHE.clear()
        i18n._VERSION_CACHE.update({"value": "", "expires_at": 0.0})
        i18n._CHAMPION_NAME_CACHE.clear()
        i18n._ITEM_NAME_CACHE.clear()
    try:
        with patch("app.i18n._schedule_locale_refresh") as schedule, patch(
            "app.i18n._fetch_latest_version",
            side_effect=AssertionError("request-path lookup should not fetch version"),
        ):
            assert champion_name("Ahri", locale="zh-CN") == "Ahri"
            assert item_name(1056, locale="zh-CN") == "\u7269\u54c1 1056"
        assert schedule.call_count == 2
    finally:
        with i18n._LOCK:
            i18n._VERSION_CACHE.clear()
            i18n._VERSION_CACHE.update(old_version)
            i18n._CHAMPION_NAME_CACHE.clear()
            i18n._CHAMPION_NAME_CACHE.update(old_champ)
            i18n._ITEM_NAME_CACHE.clear()
            i18n._ITEM_NAME_CACHE.update(old_item)


def test_zh_name_lookups_use_cached_mapping_without_refresh():
    with i18n._LOCK:
        old_version = dict(i18n._VERSION_CACHE)
        old_champ = dict(i18n._CHAMPION_NAME_CACHE)
        old_item = dict(i18n._ITEM_NAME_CACHE)
        version = "99.99.1"
        now = time.time()
        i18n._VERSION_CACHE.clear()
        i18n._VERSION_CACHE.update({"value": version, "expires_at": now + 60})
        i18n._CHAMPION_NAME_CACHE.clear()
        i18n._CHAMPION_NAME_CACHE[(version, "zh_CN")] = {
            "ahri": "\u963f\u72f8",
            "_expires_at": now + 60,
        }
        i18n._ITEM_NAME_CACHE.clear()
        i18n._ITEM_NAME_CACHE[(version, "zh_CN")] = {
            1056: "\u591a\u5170\u4e4b\u6212",
            -1: now + 60,
        }
    try:
        with patch("app.i18n._schedule_locale_refresh") as schedule:
            assert champion_name("Ahri", locale="zh-CN") == "\u963f\u72f8"
            assert item_name(1056, locale="zh-CN") == "\u591a\u5170\u4e4b\u6212"
        schedule.assert_not_called()
    finally:
        with i18n._LOCK:
            i18n._VERSION_CACHE.clear()
            i18n._VERSION_CACHE.update(old_version)
            i18n._CHAMPION_NAME_CACHE.clear()
            i18n._CHAMPION_NAME_CACHE.update(old_champ)
            i18n._ITEM_NAME_CACHE.clear()
            i18n._ITEM_NAME_CACHE.update(old_item)


def test_js_i18n_payload_includes_localized_ai_status_labels():
    payload_zh = js_i18n_payload("zh-CN")
    labels_zh = payload_zh["labels"]
    assert labels_zh["aiStatusStreaming"] == "状态：AI 实时流分析中..."
    assert labels_zh["aiStatusFailed"] == "状态：分析失败。"
    assert labels_zh["aiStatusCached"] == "状态：生成失败，已回退到缓存分析。"

    payload_en = js_i18n_payload("en")
    labels_en = payload_en["labels"]
    assert labels_en["aiStatusStreaming"] == "Status: streaming AI analysis..."
    assert labels_en["aiStatusFailed"] == "Status: analysis failed."
    assert labels_en["aiStatusCached"] == "Status: fallback to cached analysis due to generation error."


def test_js_i18n_payload_localizes_stream_fallback_labels_for_zh():
    labels_zh = js_i18n_payload("zh-CN")["labels"]
    assert labels_zh["streamFallback"].startswith("AI教练分析实时流中断")
    assert labels_zh["streamUnavailable"].startswith("当前浏览器不支持 AI 教练实时流")
    assert labels_zh["staleFallback"].startswith("AI 教练实时流返回了缓存分析")
    assert "Live stream" not in labels_zh["streamFallback"]
    assert "Live stream" not in labels_zh["streamUnavailable"]
    assert "Live stream" not in labels_zh["staleFallback"]


def test_js_i18n_payload_includes_empty_state_cta_labels():
    labels_en = js_i18n_payload("en")["labels"]
    assert labels_en["noMatchesHelp"].startswith("Connect your Riot account in settings")
    assert labels_en["goSettings"] == "Go to Settings"

    labels_zh = js_i18n_payload("zh-CN")["labels"]
    assert labels_zh["noMatchesHelp"].startswith("请先在设置中绑定 Riot 账号")
    assert labels_zh["goSettings"] == "前往设置"
