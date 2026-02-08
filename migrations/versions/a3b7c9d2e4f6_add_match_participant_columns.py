"""Add queue_type, participants_json, game_start_timestamp columns

Revision ID: a3b7c9d2e4f6
Revises: 104d8bc0e838
Create Date: 2026-02-08 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3b7c9d2e4f6'
down_revision = '104d8bc0e838'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('match_analyses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('queue_type', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('participants_json', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('game_start_timestamp', sa.BigInteger(), nullable=True))


def downgrade():
    with op.batch_alter_table('match_analyses', schema=None) as batch_op:
        batch_op.drop_column('game_start_timestamp')
        batch_op.drop_column('participants_json')
        batch_op.drop_column('queue_type')
