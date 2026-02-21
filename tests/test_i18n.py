"""Tests for locale resolution and basic bilingual rendering."""

from app.i18n import queue_label, rank_tier_label


def test_locale_defaults_to_zh_without_cookie(app, db):
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "工作流程" in body


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
    assert "工作流程" in body


def test_zh_queue_labels_use_game_terms():
    assert queue_label("Ranked Solo", locale="zh-CN") == "单/双排位"
    assert queue_label("Normal Draft", locale="zh-CN") == "召唤师峡谷（征召模式）"


def test_zh_rank_tiers_use_official_names():
    assert rank_tier_label("CHALLENGER", locale="zh-CN") == "最强王者"
    assert rank_tier_label("DIAMOND", locale="zh-CN") == "璀璨钻石"
