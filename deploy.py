"""Pre-deploy script: ensure Alembic version tracking, then run migrations."""

from sqlalchemy import inspect
from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    # Dialect-safe existence check (works for SQLite/Postgres/MySQL).
    has_alembic_version = inspect(db.engine).has_table('alembic_version')

    if not has_alembic_version:
        # Database was created by db.create_all(), not Alembic.
        # Stamp at the last migration that matches the existing schema
        # (all tables + llm_analysis column exist, but not the new 3 columns).
        from flask_migrate import stamp
        print("No alembic_version table found. Stamping database at 104d8bc0e838...")
        stamp(revision='104d8bc0e838')
        print("Done.")
    else:
        print("alembic_version table exists, skipping stamp.")
