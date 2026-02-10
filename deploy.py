"""Pre-deploy script: ensure Alembic version tracking, then run migrations."""

from sqlalchemy import inspect
from app import create_app
from app.extensions import db

INITIAL_REVISION = '6d9f34b1d861'
LLM_REVISION = '104d8bc0e838'
LATEST_REVISION = 'a3b7c9d2e4f6'


def _determine_stamp_revision(table_names: set[str], match_columns: set[str]) -> str | None:
    """Choose Alembic revision to stamp for pre-existing schemas without version tracking."""
    if not table_names:
        # Fresh empty DB: run all migrations from base (do not stamp).
        return None
    if 'match_analyses' not in table_names:
        # Unknown/partial schema: safest is to avoid stamping.
        return None

    latest_columns = {'queue_type', 'participants_json', 'game_start_timestamp'}
    if latest_columns.issubset(match_columns):
        return LATEST_REVISION
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
        if 'match_analyses' in table_names:
            match_columns = {col.get('name') for col in inspector.get_columns('match_analyses')}

        revision = _determine_stamp_revision(table_names, match_columns)
        if not revision:
            print("No alembic_version table found on empty/unknown schema. Skipping stamp.")
            return

        from flask_migrate import stamp
        print(f"No alembic_version table found. Stamping database at {revision}...")
        stamp(revision=revision)
        print("Done.")


if __name__ == '__main__':
    main()
