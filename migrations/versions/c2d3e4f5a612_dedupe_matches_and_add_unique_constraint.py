"""dedupe duplicate match rows and enforce per-user match uniqueness

Revision ID: c2d3e4f5a612
Revises: b1c2d3e4f501
Create Date: 2026-02-22 18:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2d3e4f5a612'
down_revision = 'b1c2d3e4f501'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DELETE FROM match_analyses
        WHERE id IN (
            SELECT id FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY user_id, match_id
                        ORDER BY analyzed_at DESC, id DESC
                    ) AS rn
                FROM match_analyses
            ) ranked
            WHERE rn > 1
        )
        """
    )

    with op.batch_alter_table('match_analyses', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_match_analyses_user_match', ['user_id', 'match_id'])


def downgrade():
    with op.batch_alter_table('match_analyses', schema=None) as batch_op:
        batch_op.drop_constraint('uq_match_analyses_user_match', type_='unique')
