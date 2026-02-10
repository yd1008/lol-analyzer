"""Tests for deploy bootstrap revision selection."""

from deploy import (
    INITIAL_REVISION,
    LATEST_REVISION,
    LLM_REVISION,
    _determine_stamp_revision,
)


def test_determine_stamp_revision_empty_db_returns_none():
    assert _determine_stamp_revision(set(), set()) is None


def test_determine_stamp_revision_unknown_schema_returns_none():
    assert _determine_stamp_revision({'users'}, set()) is None


def test_determine_stamp_revision_initial_schema():
    revision = _determine_stamp_revision({'users', 'match_analyses'}, {'id', 'user_id'})
    assert revision == INITIAL_REVISION


def test_determine_stamp_revision_llm_schema():
    revision = _determine_stamp_revision(
        {'users', 'match_analyses'},
        {'id', 'user_id', 'llm_analysis'},
    )
    assert revision == LLM_REVISION


def test_determine_stamp_revision_latest_schema():
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
    )
    assert revision == LATEST_REVISION
