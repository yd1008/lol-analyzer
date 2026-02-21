"""add llm language columns

Revision ID: 8f2b7d1c9a11
Revises: a3b7c9d2e4f6
Create Date: 2026-02-21 06:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8f2b7d1c9a11'
down_revision = 'a3b7c9d2e4f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('match_analyses', sa.Column('llm_analysis_en', sa.Text(), nullable=True))
    op.add_column('match_analyses', sa.Column('llm_analysis_zh', sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE match_analyses
        SET llm_analysis_en = llm_analysis
        WHERE llm_analysis IS NOT NULL
          AND (llm_analysis_en IS NULL OR llm_analysis_en = '')
        """
    )


def downgrade():
    op.drop_column('match_analyses', 'llm_analysis_zh')
    op.drop_column('match_analyses', 'llm_analysis_en')
