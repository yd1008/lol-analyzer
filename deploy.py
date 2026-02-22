"""Pre-deploy script: ensure Alembic version tracking, then run migrations."""

from sqlalchemy import inspect
from app import create_app
from app.extensions import db

INITIAL_REVISION = '6d9f34b1d861'
LLM_REVISION = '104d8bc0e838'
MATCH_CONTEXT_REVISION = 'a3b7c9d2e4f6'
LLM_LANGUAGE_REVISION = '8f2b7d1c9a11'
ADMIN_ROLE_AUDIT_REVISION = 'b1c2d3e4f501'
LATEST_REVISION = 'c2d3e4f5a612'

def _determine_stamp_revision(
    table_names: set[str],
    match_columns: set[str],
    user_columns: set[str] | None = None,
    settings_columns: set[str] | None = None,
) -> str | None:
    """Choose Alembic revision to stamp for pre-existing schemas without version tracking."""
    user_columns = user_columns or set()
    settings_columns = settings_columns or set()

    if not table_names:
        # Fresh empty DB: run all migrations from base (do not stamp).
        return None
    if 'match_analyses' not in table_names:
        # Unknown/partial schema: safest is to avoid stamping.
        return None

    match_context_columns = {'queue_type', 'participants_json', 'game_start_timestamp'}
    language_columns = {'llm_analysis_en', 'llm_analysis_zh'}
    admin_schema_present = (
        'admin_audit_logs' in table_names
        and 'role' in user_columns
        and 'preferred_locale' in settings_columns
    )
    if match_context_columns.union(language_columns).issubset(match_columns) and admin_schema_present:
        return LATEST_REVISION
    if match_context_columns.union(language_columns).issubset(match_columns):
        return LLM_LANGUAGE_REVISION
    if match_context_columns.issubset(match_columns) and admin_schema_present:
        return ADMIN_ROLE_AUDIT_REVISION
    if match_context_columns.issubset(match_columns):
        return MATCH_CONTEXT_REVISION
    if 'llm_analysis' in match_columns:
        return LLM_REVISION
    return INITIAL_REVISION


def main() -> None:
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if inspector.has_table('alembic_version'):
            print("alembic_version table exists, skipping stamp.")
            return

        table_names = set(inspector.get_table_names())
        match_columns = set()
        user_columns = set()
        settings_columns = set()
        if 'match_analyses' in table_names:
            match_columns = {col.get('name') for col in inspector.get_columns('match_analyses')}
        if 'users' in table_names:
            user_columns = {col.get('name') for col in inspector.get_columns('users')}
        if 'user_settings' in table_names:
            settings_columns = {col.get('name') for col in inspector.get_columns('user_settings')}

        revision = _determine_stamp_revision(table_names, match_columns, user_columns, settings_columns)
        if not revision:
            print("No alembic_version table found on empty/unknown schema. Skipping stamp.")
            return
        from flask_migrate import stamp
        print(f"No alembic_version table found. Stamping database at {revision}...")
        stamp(revision=revision)
        print("Done.")


if __name__ == '__main__':
    main()
