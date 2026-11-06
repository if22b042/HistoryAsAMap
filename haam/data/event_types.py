"""Which Wikidata items count as historical events.

An item is accepted only if it is an *instance of* (P31) one of ``EVENT_TYPES``
or of any of their subclasses (P279*). Order matters: when an item matches
several types, the first one in this list decides its category (so a naval
battle is "naval", not "military").

All IDs were checked against wikidata.org. Edit freely; the exporter writes the
matched type of every event into the CSV, so the effect is easy to review.
("international conference", Q18564543, was tried and dropped: it is mostly
modern ministerial meetings and UN sessions.)
"""

# (Wikidata ID, label, category)
EVENT_TYPES = [
    ("Q1261499", "naval battle", "naval"),
    ("Q178561", "battle", "military"),
    ("Q188055", "siege", "military"),
    ("Q831663", "military campaign", "military"),
    ("Q645883", "military operation", "military"),
    ("Q131569", "treaty", "diplomatic"),
    ("Q7157512", "peace conference", "diplomatic"),
    ("Q1072326", "summit", "diplomatic"),
    ("Q1464916", "declaration of independence", "diplomatic"),
    ("Q210112", "nuclear weapons testing", "scientific"),
    ("Q10931", "revolution", "other"),
    ("Q124734", "rebellion", "other"),
    ("Q45382", "coup d'état", "other"),
    ("Q3882219", "assassination", "other"),
    ("Q3199915", "massacre", "other"),
    ("Q209715", "coronation", "other"),
    ("Q2401485", "expedition", "other"),
    ("Q7692360", "volcanic eruption", "other"),
    ("Q8065", "natural disaster", "other"),
    ("Q168983", "conflagration", "other"),
]

# Rejected if the item is *directly* an instance of one of these, even when it
# also matches an event type (Wikidata items are sometimes typed as both).
NOT_EVENTS = {
    "Q5": "human",  # person items sometimes also carry "coronation" or "assassination"
    "Q486972": "human settlement",
    "Q41176": "building",
    "Q4895508": "battlefield",
    "Q82794": "region",
    "Q4167410": "Wikimedia disambiguation page",
    "Q4167836": "Wikimedia category",
    "Q13406463": "Wikimedia list article",
    "Q15275719": "recurring event",
}

# Rejected if the item is an instance of these *or any subclass* (checked in the
# discovery query), e.g. fictional battle, fictional war.
NOT_EVENT_ROOTS = {
    "Q14897293": "fictional entity",
}

# An event without its own coordinates may borrow those of its location only when
# the location is a specific place. Types (with all their subclasses) that count
# as a specific place win over AREA_ROOTS, because many cities are also typed as
# administrative regions (Berlin, Vienna, Moscow...). Locations matching neither,
# such as buildings, palaces, streets or mountains, are accepted too.
PLACE_ROOTS = {
    "Q486972": "human settlement",
    "Q515": "city",
    "Q1549591": "big city",
    "Q15284": "municipality",
    "Q123705": "neighbourhood",
    "Q2983893": "quarter",
}
# Countries, regions and bodies of water: their coordinates are only a rough centre
# (e.g. the Atlantic Ocean at 0, -30), so they never place an event on the map.
AREA_ROOTS = {
    "Q6256": "country",
    "Q3624078": "sovereign state",
    "Q3024240": "historical country",
    "Q7275": "state",
    "Q10864048": "first-level administrative division",
    "Q82794": "region",
    "Q1620908": "historical region",
    "Q5107": "continent",
    "Q9430": "ocean",
    "Q165": "sea",
    "Q46831": "mountain range",
}

# Items without a point in time / start time of their own that are typed as one of
# these are organisations or states that happen to be filed under an event type
# (Afrika Korps, UN missions, Transnistria...), not events. Wikidata files many real
# events (campaigns, coups, revolts) under "organization" too, so that class only
# counts when it is the item's direct type, and only for items without such dates.
ORGANISATION_ROOTS = {  # with all their subclasses
    "Q176799": "military unit",
    "Q7275": "state",
    "Q1048835": "political territorial entity",
}
ORGANISATION_TYPES = {  # direct types only
    "Q43229": "organization",
    "Q484652": "international organization",
    "Q136762766": "UN peacekeeping mission",
    "Q4698967": "airport authority",
    "Q16848268": "interstate compact",
}

EARTH = "http://www.wikidata.org/entity/Q2"
