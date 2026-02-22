"""add admin role, admin audit log, and preferred locale

Revision ID: b1c2d3e4f501
Revises: 8f2b7d1c9a11
Create Date: 2026-02-22 18:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f501'
down_revision = '8f2b7d1c9a11'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(length=16), nullable=False, server_default='user'))

    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('preferred_locale', sa.String(length=8), nullable=False, server_default='zh-CN'))

    op.create_table(
        'admin_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('route', sa.String(length=256), nullable=False),
        sa.Column('method', sa.String(length=16), nullable=False),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.String(length=512), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('admin_audit_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_admin_audit_logs_actor_user_id'), ['actor_user_id'], unique=False)

    op.execute("UPDATE users SET role = 'user' WHERE role IS NULL OR role = ''")
    op.execute("UPDATE user_settings SET preferred_locale = 'zh-CN' WHERE preferred_locale IS NULL OR preferred_locale = ''")


def downgrade():
    with op.batch_alter_table('admin_audit_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_admin_audit_logs_actor_user_id'))
    op.drop_table('admin_audit_logs')

    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.drop_column('preferred_locale')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('role')
