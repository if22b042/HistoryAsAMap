"""daily games and game scores

Fixes each day's game when it is first requested (``haam_daily_games``) and
keeps the anonymous totals of finished daily games (``haam_game_scores``).

Revision ID: f2b3c4d5e6a7
Revises: e1a2b3c4d5f6
Create Date: 2026-11-16 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2b3c4d5e6a7'
down_revision = 'e1a2b3c4d5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('haam_daily_games',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('hard', sa.Boolean(), nullable=False),
    sa.Column('refs', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('date', 'hard', name='uq_haam_daily_games_date_hard')
    )
    op.create_table('haam_game_scores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('hard', sa.Boolean(), nullable=False),
    sa.Column('points', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('haam_game_scores', schema=None) as batch_op:
        batch_op.create_index('ix_haam_game_scores_date_hard', ['date', 'hard'], unique=False)


def downgrade():
    with op.batch_alter_table('haam_game_scores', schema=None) as batch_op:
        batch_op.drop_index('ix_haam_game_scores_date_hard')
    op.drop_table('haam_game_scores')
    op.drop_table('haam_daily_games')
