"""game score proof

Each daily score now comes from signed round tokens; ``proof`` is their hash,
unique so that one finished game is counted once.

Revision ID: b4d5e6f7a8c9
Revises: a3c4d5e6f7b8
Create Date: 2026-11-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4d5e6f7a8c9'
down_revision = 'a3c4d5e6f7b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('haam_game_scores', schema=None) as batch_op:
        batch_op.add_column(sa.Column('proof', sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint('uq_haam_game_scores_proof', ['proof'])


def downgrade():
    with op.batch_alter_table('haam_game_scores', schema=None) as batch_op:
        batch_op.drop_constraint('uq_haam_game_scores_proof', type_='unique')
        batch_op.drop_column('proof')
