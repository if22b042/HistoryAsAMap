"""event month and day

Stores the month and day of day-precise dates, for "On this day" on the map.
They are parsed from ``date_label``; labels of Wikidata imports were written
from Wikidata's own day-precise time values, so they carry the same date.

Revision ID: d4e5f6a7b8c9
Revises: c3f1d2a4b5e6
Create Date: 2026-11-08 10:00:00.000000

"""
from collections import defaultdict

from alembic import op
import sqlalchemy as sa

from haam.dates import month_day


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3f1d2a4b5e6'
branch_labels = None
depends_on = None

CHUNK = 500


def upgrade():
    with op.batch_alter_table('haam_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('month', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('day', sa.Integer(), nullable=True))
        batch_op.create_index('ix_haam_events_month_day', ['month', 'day'], unique=False)

    events = sa.table('haam_events', sa.column('id', sa.Integer), sa.column('date_label', sa.String),
                      sa.column('month', sa.Integer), sa.column('day', sa.Integer))
    bind = op.get_bind()
    by_day = defaultdict(list)
    for event_id, label in bind.execute(sa.select(events.c.id, events.c.date_label)):
        parsed = month_day(label)
        if parsed:
            by_day[parsed].append(event_id)
    # One UPDATE per calendar day (at most 366), not one per event.
    for (month, day), ids in by_day.items():
        for start in range(0, len(ids), CHUNK):
            bind.execute(events.update().where(events.c.id.in_(ids[start:start + CHUNK]))
                         .values(month=month, day=day))


def downgrade():
    with op.batch_alter_table('haam_events', schema=None) as batch_op:
        batch_op.drop_index('ix_haam_events_month_day')
        batch_op.drop_column('day')
        batch_op.drop_column('month')
