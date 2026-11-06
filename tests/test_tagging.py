from haam.tagging import ChainResolver, TagMatcher, normalise

TAGS = [
    ("American Revolution", 1765, 1783),
    ("American Revolutionary War", 1775, 1783),
    ("French Revolution", 1789, 1799),
    ("Napoleonic Wars", 1803, 1815),
    ("Napoleonic Era", 1799, 1815),
    ("World War II", 1939, 1945),
    ("War on Terror", 2001, None),
]


def test_normalise():
    assert normalise("The Seven Years’ War") == normalise("seven years' war") == "seven years war"
    assert normalise("Russo–Japanese War") == normalise("Russo-Japanese war")
    assert normalise("Révolution") == "revolution"


def test_matcher_adds_parents_and_checks_years():
    matcher = TagMatcher(TAGS, parents={"American Revolutionary War": ["American Revolution"],
                                        "Napoleonic Wars": ["Napoleonic Era"]})
    assert matcher.match(["american revolutionary war"], 1775) == ["American Revolution", "American Revolutionary War"]
    # Austerlitz' chain reaches the French Revolution, but 1805 is outside its years.
    assert matcher.match(["Napoleonic Wars", "French Revolution"], 1805) == ["Napoleonic Era", "Napoleonic Wars"]
    assert matcher.match(["War on Terror"], 2021) == ["War on Terror"]  # still ongoing
    assert matcher.match(["Something else"], 1900) == []


def test_matcher_only_uses_known_tags():
    matcher = TagMatcher(TAGS, parents={}, only=["World War II"])
    assert matcher.match(["World War II", "American Revolution"], 1942) == ["World War II"]


class FakeClient:
    def __init__(self, items):
        self.items, self.calls = items, 0

    def entities(self, ids, props="claims"):
        self.calls += 1
        result = {}
        for qid in ids:
            if qid in self.items:
                label, aliases, parents = self.items[qid]
                result[qid] = {
                    "labels": {"en": {"value": label}},
                    "aliases": {"en": [{"value": a} for a in aliases]},
                    "claims": {"P361": [{"rank": "normal", "mainsnak": {"snaktype": "value",
                                         "datavalue": {"value": {"id": p}}}} for p in parents]},
                }
        return result


def test_chain_resolver_follows_part_of_and_aliases():
    client = FakeClient({
        "Q1": ("Battles of Saratoga", [], ["Q2"]),
        "Q2": ("American Revolutionary War", ["American War of Independence"], ["Q3"]),
        "Q3": ("American Revolution", [], ["Q3"]),  # a loop must not hang
    })
    chains = ChainResolver(client).resolve({"freemans-farm": ["Q1"], "lexington": ["Q2"], "alone": []})
    assert chains["freemans-farm"] == {"Battles of Saratoga", "American Revolutionary War",
                                       "American War of Independence", "American Revolution"}
    assert chains["lexington"] == {"American Revolutionary War", "American War of Independence", "American Revolution"}
    assert chains["alone"] == set()
    assert client.calls == 2  # one request per level, shared by all events


def test_retag_database_adds_missing_tags_only(app, make_event):
    from haam.extensions import db
    from haam.models import Tag
    from haam.tagging import retag_database

    def part_of(*ids):
        return {"P361": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": i}}}}
                         for i in ids]}

    class Client(FakeClient):
        def entities(self, ids, props="claims"):
            result = super().entities(ids, props)
            result.update({"Q100": {"claims": part_of("Q2")}, "Q101": {"claims": {}}})
            return {k: v for k, v in result.items() if k in ids}

    client = Client({"Q2": ("American Revolutionary War", [], ["Q3"]), "Q3": ("American Revolution", [], [])})
    db.session.add_all([Tag(name="American Revolution", start_year=1765, end_year=1783),
                        Tag(name="American Revolutionary War", start_year=1775, end_year=1783),
                        Tag(name="Industrial Revolution", start_year=1760, end_year=1840)])
    db.session.commit()
    lexington = make_event(title="Battles of Lexington and Concord", year=1775, wikidata_id="Q100")
    manual = db.session.scalar(db.select(Tag).filter_by(name="Industrial Revolution"))
    lexington.tags = [db.session.scalar(db.select(Tag).filter_by(name="American Revolutionary War")), manual]
    make_event(title="Unrelated", year=1775, wikidata_id="Q101")
    db.session.commit()

    dry = retag_database(client, dry_run=True, report=lambda m: None)
    assert (dry["links_added"], dry["events_changed"]) == (1, 1)
    assert len(lexington.tags) == 2

    stats = retag_database(client, report=lambda m: None)
    db.session.refresh(lexington)
    assert stats["links_added"] == 1
    assert sorted(t.name for t in lexington.tags) == ["American Revolution", "American Revolutionary War",
                                                     "Industrial Revolution"]  # the manual tag stays
    assert retag_database(client, report=lambda m: None)["links_added"] == 0  # safe to re-run


def test_chain_resolver_does_not_climb_through_bridging_items():
    client = FakeClient({
        "Q1": ("Mali War", [], ["Q17507684", "Q4"]),
        "Q17507684": ("War against the Islamic State", [], ["Q5"]),
        "Q4": ("War on Terror", [], []),
        "Q5": ("Syrian Civil War", [], []),
    })
    chains = ChainResolver(client).resolve({"tessit": ["Q1"]})
    assert chains["tessit"] == {"Mali War", "War against the Islamic State", "War on Terror"}


def test_wars_end_sharply_but_may_start_a_year_early():
    matcher = TagMatcher([("World War II", 1939, 1945), ("Seven Years' War", 1756, 1763)], parents={})
    assert matcher.match(["World War II"], 1945) == ["World War II"]
    assert matcher.match(["World War II"], 1946) == []  # Attack on Hrubieszów
    assert matcher.match(["Seven Years' War"], 1755) == ["Seven Years' War"]  # Battle of Lake George


def test_excluded_direct_links():
    from haam.tagging import Tagger

    tagger = Tagger(FakeClient({"Q8683": ("Cold War", [], [])}), ["Cold War"])
    tags = tagger.tags({"Q96363613": ["Q8683"], "Q1": ["Q8683"]}, {"Q96363613": 1978, "Q1": 1978})
    assert tags == {"Q96363613": [], "Q1": ["Cold War"]}  # only the listed event loses the tag


def test_retag_database_replace_removes_and_skips_website_events(app, make_event):
    from haam.extensions import db
    from haam.models import Tag
    from haam.tagging import retag_database

    class Client(FakeClient):
        def entities(self, ids, props="claims"):
            return {i: {"claims": {}} for i in ids}  # no "part of": the rules give no tags

    cold_war = Tag(name="Cold War", start_year=1947, end_year=1991)
    db.session.add(cold_war)
    imported = make_event(title="Battle of Zahleh", year=1980, wikidata_id="Q4872802")
    submitted = make_event(title="Submitted", year=1980, wikidata_id="Q5", from_website=True)
    imported.tags, submitted.tags = [cold_war], [cold_war]
    db.session.commit()

    assert retag_database(Client({}), report=lambda m: None)["links_removed"] == 0  # default: only adds
    stats = retag_database(Client({}), replace=True, report=lambda m: None)
    db.session.refresh(imported)
    db.session.refresh(submitted)
    assert (stats["links_removed"], imported.tags, [t.name for t in submitted.tags]) == (1, [], ["Cold War"])
