"""event from_website flag

Marks events submitted through "Add event", so the admin pages can tell them
apart from bulk imports. Existing rows count as imports.

Revision ID: c3f1d2a4b5e6
Revises: 8aa70bfe4e79
Create Date: 2026-11-06 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f1d2a4b5e6'
down_revision = '8aa70bfe4e79'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('haam_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('from_website', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    with op.batch_alter_table('haam_events', schema=None) as batch_op:
        batch_op.drop_column('from_website')
