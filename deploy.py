"""Pre-deploy script: ensure Alembic version tracking, then run migrations."""

import sys
from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    # Check if alembic_version table exists
    result = db.session.execute(
        db.text("SELECT count(*) FROM information_schema.tables WHERE table_name='alembic_version'")
    ).scalar()
    db.session.close()

    if not result:
        # Database was created by db.create_all(), not Alembic.
        # Stamp at the last migration that matches the existing schema
        # (all tables + llm_analysis column exist, but not the new 3 columns).
        from flask_migrate import stamp
        print("No alembic_version table found. Stamping database at 104d8bc0e838...")
        stamp(revision='104d8bc0e838')
        print("Done.")
    else:
        print("alembic_version table exists, skipping stamp.")
