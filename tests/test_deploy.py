"""Tests for deploy bootstrap revision selection."""

from deploy import (
    ADMIN_ROLE_AUDIT_REVISION,
    INITIAL_REVISION,
    LATEST_REVISION,
    LLM_REVISION,
    LLM_LANGUAGE_REVISION,
    MATCH_CONTEXT_REVISION,
    _determine_stamp_revision,
)


def test_determine_stamp_revision_empty_db_returns_none():
    assert _determine_stamp_revision(set(), set(), set(), set()) is None


def test_determine_stamp_revision_unknown_schema_returns_none():
    assert _determine_stamp_revision({'users'}, set(), set(), set()) is None


def test_determine_stamp_revision_initial_schema():
    revision = _determine_stamp_revision({'users', 'match_analyses'}, {'id', 'user_id'}, {'id'}, {'id'})
    assert revision == INITIAL_REVISION


def test_determine_stamp_revision_llm_schema():
    revision = _determine_stamp_revision(
        {'users', 'match_analyses'},
        {'id', 'user_id', 'llm_analysis'},
        {'id'},
        {'id'},
    )
    assert revision == LLM_REVISION


def test_determine_stamp_revision_match_context_schema():
    revision = _determine_stamp_revision(
        {'users', 'match_analyses'},
        {
            'id',
            'user_id',
            'llm_analysis',
            'queue_type',
            'participants_json',
            'game_start_timestamp',
        },
        {'id'},
        {'id'},
    )
    assert revision == MATCH_CONTEXT_REVISION


def test_determine_stamp_revision_language_schema_without_admin_tables():
    revision = _determine_stamp_revision(
        {'users', 'match_analyses', 'user_settings'},
        {
            'id',
            'user_id',
            'llm_analysis',
            'queue_type',
            'participants_json',
            'game_start_timestamp',
            'llm_analysis_en',
            'llm_analysis_zh',
        },
        {'id'},
        {'id'},
    )
    assert revision == LLM_LANGUAGE_REVISION


def test_determine_stamp_revision_admin_role_audit_schema():
    revision = _determine_stamp_revision(
        {'users', 'match_analyses', 'user_settings', 'admin_audit_logs'},
        {
            'id',
            'user_id',
            'llm_analysis',
            'queue_type',
            'participants_json',
            'game_start_timestamp',
            'llm_analysis_en',
            'llm_analysis_zh',
        },
        {'id', 'role'},
        {'id', 'preferred_locale'},
    )
    assert revision == LATEST_REVISION


def test_determine_stamp_revision_admin_role_audit_before_unique_revision():
    revision = _determine_stamp_revision(
        {'users', 'match_analyses', 'user_settings', 'admin_audit_logs'},
        {
            'id',
            'user_id',
            'llm_analysis',
            'queue_type',
            'participants_json',
            'game_start_timestamp',
        },
        {'id', 'role'},
        {'id', 'preferred_locale'},
    )
    assert revision == ADMIN_ROLE_AUDIT_REVISION
