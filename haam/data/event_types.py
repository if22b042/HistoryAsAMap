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

EARTH = "http://www.wikidata.org/entity/Q2"
