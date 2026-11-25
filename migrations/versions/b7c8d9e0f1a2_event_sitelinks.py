"""event sitelinks: how many wikis (mostly Wikipedia languages) cover the event

Filled by `flask haam fetch-sitelinks` (and kept by `sync-wikidata` from the CSV).
Existing rows get 0, which means "unknown".

Revision ID: b7c8d9e0f1a2
Revises: c5d6e7f8a9b0
"""
import sqlalchemy as sa
from alembic import op

revision = 'b7c8d9e0f1a2'
down_revision = 'c5d6e7f8a9b0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('haam_events') as batch:
        batch.add_column(sa.Column('sitelinks', sa.Integer(), server_default='0', nullable=False))


def downgrade():
    with op.batch_alter_table('haam_events') as batch:
        batch.drop_column('sitelinks')
