"""fold violence into disaster

"Violence" (massacres, terrorist attacks...) and "disaster" (fires, explosions,
accidents...) become one category, "disaster": human-made disasters of any kind.
Assassinations and single murders are not disasters, so the 126 imported events
that were "violence" only because of those classes go back to "other" (listed
below by Wikidata id, worked out on 2026-11-09 with the narrowed rules of
``haam.wikidata.refine_category``). Everything else that was "violence",
including collection entries, becomes "disaster".

The downgrade restores "violence" for the events migration 7b2f9c41d8a3 put
there.

Revision ID: a91c3e5f7b20
Revises: 7b2f9c41d8a3
Create Date: 2026-11-09 12:00:00.000000

"""
import importlib.util
from pathlib import Path

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a91c3e5f7b20'
down_revision = '7b2f9c41d8a3'
branch_labels = None
depends_on = None

# Were "violence", now "other": assassinations and murders.
BACK_TO_OTHER = """
Q1003866 Q100785585 Q1025404 Q104843847 Q105359547 Q105570 Q105987834 Q1062771 Q106784655 Q107442287
Q107487842 Q108196142 Q108336746 Q10858950 Q10858954 Q109392668 Q111968653 Q11256383 Q112872231
Q112967003 Q113213574 Q114849614 Q116413522 Q117077158 Q1187550 Q120738963 Q121334219 Q123139694
Q124079910 Q124086310 Q124556504 Q125257835 Q125783158 Q125894913 Q127607598 Q128172378 Q12881562
Q130374882 Q130974174 Q131389544 Q131564576 Q133808703 Q134179492 Q134734156 Q136001786 Q136009028
Q136163041 Q136210698 Q137593921 Q138507700 Q138715235 Q141286895 Q15220596 Q1578660 Q16199212
Q1634609 Q16529009 Q17621744 Q19085 Q193484 Q19362904 Q19865025 Q20650851 Q21005831 Q23020255
Q23296653 Q2362167 Q244926 Q2475091 Q2529018 Q2608162 Q2665185 Q28036166 Q28055289 Q2866969 Q2866970
Q2866972 Q2866974 Q2866985 Q28798841 Q2903305 Q29514943 Q3284177 Q3347903 Q3350154 Q3444768
Q39057172 Q3975708 Q4118404 Q41725020 Q42378006 Q43380540 Q4634100 Q46603 Q4808502 Q4808506 Q4808507
Q4808510 Q4808511 Q4808516 Q4808518 Q4808524 Q4808525 Q4808531 Q482859 Q48867324 Q50667990 Q5365139
Q5396821 Q5708121 Q57527214 Q60614851 Q60761103 Q60832021 Q60836410 Q61995994 Q623757 Q63522033
Q64831559 Q65058927 Q65613535 Q714535 Q757963 Q80754846 Q9385537 Q975430
"""

events = sa.table('haam_events', sa.column('category', sa.String), sa.column('wikidata_id', sa.String))
entries = sa.table('haam_collection_entries', sa.column('custom_category', sa.String))


def _chunks(ids, size=500):
    for start in range(0, len(ids), size):
        yield ids[start:start + size]


def _previous_violence_ids():
    """The Wikidata ids migration 7b2f9c41d8a3 moved into "violence"."""
    path = next(Path(__file__).parent.glob("7b2f9c41d8a3_*.py"))
    spec = importlib.util.spec_from_file_location("categories_7b2f9c41d8a3", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [qid for _, new, ids in module.MOVES if new == "violence" for qid in ids.split()]


def upgrade():
    for part in _chunks(BACK_TO_OTHER.split()):
        op.execute(events.update().where(events.c.wikidata_id.in_(part), events.c.category == "violence")
                   .values(category="other"))
    op.execute(events.update().where(events.c.category == "violence").values(category="disaster"))
    op.execute(entries.update().where(entries.c.custom_category == "violence").values(custom_category="disaster"))


def downgrade():
    back = set(BACK_TO_OTHER.split())
    for part in _chunks(sorted(back)):
        op.execute(events.update().where(events.c.wikidata_id.in_(part), events.c.category == "other")
                   .values(category="violence"))
    rest = [qid for qid in _previous_violence_ids() if qid not in back]
    for part in _chunks(rest):
        op.execute(events.update().where(events.c.wikidata_id.in_(part), events.c.category == "disaster")
                   .values(category="violence"))
