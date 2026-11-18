"""collection suggestions

Visitors can suggest an entry for a collection; the owner accepts or dismisses it.

Revision ID: e1a2b3c4d5f6
Revises: a91c3e5f7b20
Create Date: 2026-11-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1a2b3c4d5f6'
down_revision = 'a91c3e5f7b20'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('haam_collection_suggestions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('collection_id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=True),
    sa.Column('link', sa.String(length=500), nullable=True),
    sa.Column('message', sa.String(length=500), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['collection_id'], ['haam_collections.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['event_id'], ['haam_events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('haam_collection_suggestions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_haam_collection_suggestions_collection_id'), ['collection_id'], unique=False)


def downgrade():
    with op.batch_alter_table('haam_collection_suggestions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_haam_collection_suggestions_collection_id'))

    op.drop_table('haam_collection_suggestions')
