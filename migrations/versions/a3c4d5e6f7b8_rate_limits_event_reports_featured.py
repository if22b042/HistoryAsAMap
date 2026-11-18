"""rate limits, event reports, featured collections

Adds the table the database-backed rate limiter counts in, the table for
visitors' reports about events, and the editor's "featured" flag on collections.

Revision ID: a3c4d5e6f7b8
Revises: f2b3c4d5e6a7
Create Date: 2026-11-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3c4d5e6f7b8'
down_revision = 'f2b3c4d5e6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('haam_rate_limits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('scope', sa.String(length=40), nullable=False),
    sa.Column('client_hash', sa.String(length=64), nullable=False),
    sa.Column('window_start', sa.Integer(), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('scope', 'client_hash', 'window_start', name='uq_haam_rate_limits_window')
    )
    with op.batch_alter_table('haam_rate_limits', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_haam_rate_limits_window_start'), ['window_start'], unique=False)

    op.create_table('haam_event_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('message', sa.String(length=1000), nullable=False),
    sa.Column('proposed_year', sa.Integer(), nullable=True),
    sa.Column('proposed_date_label', sa.String(length=120), nullable=True),
    sa.Column('proposed_lat', sa.Float(), nullable=True),
    sa.Column('proposed_lon', sa.Float(), nullable=True),
    sa.Column('status', sa.Enum('open', 'applied', 'dismissed', name='reportstatus', native_enum=False, length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['haam_events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('haam_event_reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_haam_event_reports_event_id'), ['event_id'], unique=False)

    with op.batch_alter_table('haam_collections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_featured', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    with op.batch_alter_table('haam_collections', schema=None) as batch_op:
        batch_op.drop_column('is_featured')

    with op.batch_alter_table('haam_event_reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_haam_event_reports_event_id'))

    op.drop_table('haam_event_reports')
    with op.batch_alter_table('haam_rate_limits', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_haam_rate_limits_window_start'))

    op.drop_table('haam_rate_limits')
