"""A small, fixed set of events for the browser tests – built offline, no Wikipedia."""

from dataclasses import dataclass, field

from haam import collections_service
from haam.extensions import db
from haam.models import Category, Event, Status, Tag
from haam.wikipedia import canonical_url

TAGS = [
    ("Greco-Persian Wars", -499, -449),
    ("Punic Wars", -264, -146),
    ("Scientific Revolution", 1543, 1687),
    ("Napoleonic Wars", 1803, 1815),
    ("American Civil War", 1861, 1865),
    ("World War II", 1939, 1945),
]

M, D, N, S, NAT, O = (Category.MILITARY, Category.DIPLOMATIC, Category.NAVAL,
                      Category.SCIENTIFIC, Category.NATURAL, Category.OTHER)

# title, year, date label, lat, lon, category, tag names
EVENTS = [
    ("Battle of Marathon", -490, "490 BC", 38.118, 23.978, M, ["Greco-Persian Wars"]),
    ("Battle of Salamis", -480, "480 BC", 37.950, 23.566, N, ["Greco-Persian Wars"]),
    ("Battle of Thermopylae", -480, "480 BC", 38.796, 22.536, M, ["Greco-Persian Wars"]),
    ("Battle of the Aegates", -241, "10 March 241 BC", 37.970, 12.200, N, ["Punic Wars"]),
    ("Battle of Cannae", -216, "2 August 216 BC", 41.306, 16.132, M, ["Punic Wars"]),
    ("Battle of Zama", -202, "202 BC", 36.300, 9.450, M, ["Punic Wars"]),
    ("Assassination of Julius Caesar", -44, "15 March 44 BC", 41.8955, 12.4768, O, []),
    ("Battle of the Teutoburg Forest", 9, "AD 9", 52.400, 8.130, M, []),
    ("Battle of Hastings", 1066, "14 October 1066", 50.911, 0.487, M, []),
    ("Sealing of Magna Carta", 1215, "15 June 1215", 51.444, -0.565, D, []),
    ("Fall of Constantinople", 1453, "29 May 1453", 41.008, 28.978, M, []),
    ("Publication of De revolutionibus", 1543, "1543", 49.452, 11.077, S, ["Scientific Revolution"]),
    ("Discovery of the Galilean moons", 1610, "January 1610", 45.406, 11.876, S, ["Scientific Revolution"]),
    ("Peace of Westphalia", 1648, "24 October 1648", 51.962, 7.626, D, []),
    ("Publication of the Principia", 1687, "5 July 1687", 51.507, -0.128, S, ["Scientific Revolution"]),
    ("Lisbon earthquake", 1755, "1 November 1755", 38.722, -9.139, NAT, []),
    ("Battle of Trafalgar", 1805, "21 October 1805", 36.183, -6.033, N, ["Napoleonic Wars"]),
    ("Battle of Austerlitz", 1805, "2 December 1805", 49.128, 16.762, M, ["Napoleonic Wars"]),
    ("Battle of Borodino", 1812, "7 September 1812", 55.523, 35.818, M, ["Napoleonic Wars"]),
    ("Battle of Waterloo", 1815, "18 June 1815", 50.680, 4.412, M, ["Napoleonic Wars"]),
    ("Congress of Vienna", 1815, "9 June 1815", 48.208, 16.373, D, ["Napoleonic Wars"]),
    ("Eruption of Mount Tambora", 1815, "10 April 1815", -8.250, 118.000, NAT, []),
    ("Battle of Hampton Roads", 1862, "8 March 1862", 36.983, -76.333, N, ["American Civil War"]),
    ("Battle of Antietam", 1862, "17 September 1862", 39.473, -77.745, M, ["American Civil War"]),
    ("Battle of Gettysburg", 1863, "1 July 1863", 39.811, -77.226, M, ["American Civil War"]),
    ("Surrender at Appomattox", 1865, "9 April 1865", 37.377, -78.796, D, ["American Civil War"]),
    ("Eruption of Krakatoa", 1883, "27 August 1883", -6.102, 105.423, NAT, []),
    ("First flight of the Wright Flyer", 1903, "17 December 1903", 36.019, -75.668, S, []),
    ("Battle of Midway", 1942, "4 June 1942", 28.208, -177.379, N, ["World War II"]),
    ("Battle of Stalingrad", 1942, "23 August 1942", 48.708, 44.513, M, ["World War II"]),
    ("Normandy landings", 1944, "6 June 1944", 49.340, -0.600, M, ["World War II"]),
    ("Yalta Conference", 1945, "4 February 1945", 44.468, 34.143, D, ["World War II"]),
    ("Trinity nuclear test", 1945, "16 July 1945", 33.677, -106.475, S, ["World War II"]),
    ("Launch of Apollo 11", 1969, "16 July 1969", 28.573, -80.649, S, []),
]

# Waiting for review; its summary is too short for the game, so approving it in the
# admin test never changes which events the game picks.
PENDING = ("Eruption of Mount Vesuvius", 79, "24 August AD 79", 40.821, 14.426, NAT, [])

FILLER = (" Historians have written about it at length, and it is remembered in books, paintings"
          " and films. Its causes and its consequences are still debated today, and many places"
          " near where it happened keep its memory alive with monuments and museums.")


@dataclass
class Seed:
    tag_ids: dict[str, int] = field(default_factory=dict)
    event_ids: dict[str, int] = field(default_factory=dict)
    approved_count: int = 0
    pending_title: str = PENDING[0]
    public_collection_title: str = ""
    public_collection_token: str = ""


def _event(row, status: Status, summary: str, tags: dict[str, Tag]) -> Event:
    title, year, date_label, lat, lon, category, tag_names = row
    return Event(
        title=title, year=year, date_label=date_label, summary=summary,
        wiki_url=canonical_url(title), lat=lat, lon=lon, category=category, status=status,
        tags=[tags[name] for name in tag_names],
    )


def build() -> Seed:
    """Fill the (empty) database of the current app context; returns ids for the tests."""
    seed = Seed()
    tags = {name: Tag(name=name, start_year=start, end_year=end) for name, start, end in TAGS}
    db.session.add_all(tags.values())
    events = [_event(row, Status.APPROVED, f"The {row[0]} took place in {row[2]}." + FILLER, tags)
              for row in EVENTS]
    events.append(_event(PENDING, Status.PENDING, "A volcano buried two Roman towns.", tags))
    db.session.add_all(events)
    db.session.commit()

    seed.tag_ids = {name: tag.id for name, tag in tags.items()}
    seed.event_ids = {event.title: event.id for event in events}
    seed.approved_count = len(EVENTS)

    collection, _edit_token = collections_service.create_collection(
        "Ancient battles", "Battles fought before AD 500.", is_public=True)
    collections_service.add_tag_events(collection, tags["Greco-Persian Wars"].id)
    seed.public_collection_title = collection.title
    seed.public_collection_token = collection.view_token
    return seed
