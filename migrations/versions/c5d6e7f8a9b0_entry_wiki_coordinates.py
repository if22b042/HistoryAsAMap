"""collection entries: Wikipedia coordinates for manually reconfirmed places

Revision ID: c5d6e7f8a9b0
Revises: b4d5e6f7a8c9
"""
import sqlalchemy as sa
from alembic import op

revision = 'c5d6e7f8a9b0'
down_revision = 'b4d5e6f7a8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('haam_collection_entries') as batch:
        batch.add_column(sa.Column('wiki_lat', sa.Float(), nullable=True))
        batch.add_column(sa.Column('wiki_lon', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('haam_collection_entries') as batch:
        batch.drop_column('wiki_lon')
        batch.drop_column('wiki_lat')
