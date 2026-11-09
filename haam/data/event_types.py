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
    ("Q3882219", "assassination", "violence"),
    ("Q3199915", "massacre", "violence"),
    ("Q209715", "coronation", "other"),
    ("Q2401485", "expedition", "other"),
    ("Q7692360", "volcanic eruption", "natural"),
    ("Q8065", "natural disaster", "natural"),
    ("Q168983", "conflagration", "disaster"),  # fires; wildfires are refined below
]

# The discovery type gives a first, broad category. Items found as "natural
# disaster", "conflagration" or one of the "other" types are a mix (a building fire
# is not a natural disaster, a massacre found as a rebellion is not just "other"),
# so their category is refined from the item's own P31 classes, each checked with
# all its subclasses, in this order (see haam.wikidata.refine_category):
#
# 1. violence  – massacres, assassinations, terrorist attacks...  -> "violence"
# (rules 2-5 only apply to natural / disaster items: a coup that burned a
#  palace stays "other")
# 2. natural   – earthquakes, eruptions, storms, floods...          -> "natural"
#                (an earthquake that set a city on fire stays natural)
# 3. human-made – explosions, accidents, collapses, building fires  -> "disaster"
# 4. wildfire  – "disaster" if its cause (P828 / P1478) is a human
#                one (arson, slash-and-burn, cigarette...), otherwise
#                "natural": most wildfires are started by lightning or
#                have no recorded cause
# 5. fire      – any other fire                                     -> "disaster"
# 6. otherwise the broad category stays.
#
# The rules only touch these broad categories; battles, treaties etc. keep theirs.
REFINED_CATEGORIES = {"natural", "disaster", "other"}

CATEGORY_CLASSES = {  # group -> {Wikidata ID: label}, each with all its subclasses
    "violence": {
        "Q3199915": "massacre",
        "Q750215": "mass murder",
        "Q21480300": "mass shooting",
        "Q2223653": "terrorist attack",
        "Q891854": "bombing",
        "Q3882219": "assassination",
        "Q132821": "murder",
        "Q135010": "war crime",
        "Q41397": "genocide",
        "Q177716": "pogrom",
    },
    "natural": {
        "Q7944": "earthquake",
        "Q7692360": "volcanic eruption",
        "Q8070": "tsunami",
        "Q8068": "flood",
        "Q81054": "storm",
        "Q8092": "tropical cyclone",
        "Q8081": "tornado",
        "Q167903": "landslide",
        "Q7935": "avalanche",
        "Q43059": "drought",
        "Q215864": "heat wave",
        "Q642683": "cold wave",
        "Q1277161": "extreme weather event",
    },
    "human_made": {
        "Q118301709": "man-made disaster",
        "Q179057": "explosion",
        "Q327541": "arson",
        "Q171558": "accident",
        "Q11822042": "transport accident",
        "Q68800046": "industrial disaster",
        "Q15725976": "nuclear disaster",
        "Q1309431": "building collapse",
        "Q11620651": "bridge collapse",
        "Q1033074": "dam failure",
        "Q906512": "shipwreck",
        "Q2620513": "maritime disaster",
        "Q7625093": "structure fire",
        "Q838718": "city fire",
        "Q350929": "vehicle fire",
        "Q18215814": "tunnel fire",
        "Q17094485": "industrial fire",
    },
    "wildfire": {
        "Q169950": "wildfire",
    },
    "fire": {
        "Q168983": "conflagration",
        "Q3196": "fire",
    },
}

# Subclasses (with theirs) that a group must not include although Wikidata files
# them under one of its classes: the Dublin whiskey fire is a "non-water flood".
CATEGORY_CLASS_EXCLUSIONS = {
    "natural": {"Q113549847": "non-water flood"},
}

CATEGORY_CLASSES["human_cause"] = {
    # Causes (P828 "has cause", P1478 "has immediate cause") that make a wildfire man-made.
    "Q327541": "arson",
    "Q5": "human",
    "Q622543": "slash-and-burn",
    "Q3043226": "clearing",
    "Q1578": "cigarette",
    "Q131172": "welding",
    "Q5937752": "human error",
    "Q206907": "short circuit",
    "Q171558": "accident",
    "Q5526351": "gas leak",
    "Q118301709": "man-made disaster",
}

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
