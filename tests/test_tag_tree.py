import json

from haam.models import Status, Tag
from haam.tag_tree import PartOfGraph, TreeEvent, build_graph, build_tree, load_graph, narrower_tags
from tests.test_tagging import FakeClient

# World War II (Q362) > European theatre (Q2) > Eastern Front (Q3) > Operation Barbarossa (Q4) > battles
GRAPH = PartOfGraph(
    parents={
        "Q2": ["Q362"],
        "Q3": ["Q2"],
        "Q4": ["Q3"],
        "Q10": ["Q4"],  # Battle of Białystok–Minsk
        "Q11": ["Q4", "Q362"],  # Battle of Kiev: part of Barbarossa and of the war itself
        "Q12": ["Q3"],  # Battle of Stalingrad
        "Q13": ["Q12"],  # Operation Uranus, part of Stalingrad (also an event)
        "Q20": ["Q21"],  # Battle of Midway > Pacific War (its own tag)
        "Q21": ["Q362"],
        "Q30": ["Q31"],  # loop with no way to the war
        "Q31": ["Q30"],
    },
    labels={"Q362": "World War II", "Q2": "European theatre of World War II", "Q3": "Eastern Front",
            "Q4": "Operation Barbarossa", "Q12": "Battle of Stalingrad", "Q21": "Pacific War"},
    tag_items={"World War II": ["Q362"], "Pacific War": ["Q21"]},
)

EVENTS = [
    TreeEvent(1, "Q10", "Battle of Białystok–Minsk", 1941),
    TreeEvent(2, "Q11", "Battle of Kiev", 1941),
    TreeEvent(3, "Q12", "Battle of Stalingrad", 1942),
    TreeEvent(4, "Q13", "Operation Uranus", 1942),
    TreeEvent(5, "Q20", "Battle of Midway", 1942),
    TreeEvent(6, "Q30", "Something linked in a loop", 1943),
    TreeEvent(7, None, "Submitted on the website", 1944),
    TreeEvent(8, "Q99", "No part-of link", 1940),
]


def labels(node):
    return [child.label for child in node.children]


def find(node, label):
    if node.label == label:
        return node
    for child in node.children:
        hit = find(child, label)
        if hit:
            return hit
    return None


def test_tree_follows_the_chain_and_counts_every_event_once():
    tree = build_tree("World War II", EVENTS, GRAPH, tag_id=1, tag_ids={"Pacific War": 2})
    assert tree.count == len(EVENTS)
    european = find(tree, "European theatre of World War II")
    assert european.count == 4
    # equal counts: the older branch first
    assert labels(find(tree, "Eastern Front")) == ["Operation Barbarossa", "Battle of Stalingrad"]
    assert (find(tree, "Eastern Front").first, find(tree, "Eastern Front").last) == (1941, 1942)
    # the longest (most specific) path wins: Kiev goes under Barbarossa, not straight under the war
    assert labels(find(tree, "Operation Barbarossa")) == ["Battle of Białystok–Minsk", "Battle of Kiev"]
    stalingrad = find(tree, "Battle of Stalingrad")
    assert stalingrad.event_id == 3 and stalingrad.count == 2 and labels(stalingrad) == ["Operation Uranus"]
    pacific = find(tree, "Pacific War")
    assert pacific.tag_id == 2 and pacific.event_id is None and pacific.count == 1


def test_every_level_is_sorted_by_count_then_year():
    tree = build_tree("World War II", EVENTS, GRAPH)
    assert labels(tree)[0] == "European theatre of World War II"
    counts = [child.count for child in tree.children]
    assert counts == sorted(counts, reverse=True)
    # the single events directly under the war, oldest first
    singles = [c for c in tree.children if c.count == 1 and not c.children]
    assert [c.year for c in singles] == sorted(c.year for c in singles)
    assert {c.label for c in singles} == {"Something linked in a loop", "Submitted on the website", "No part-of link"}


def test_to_dict_is_compact():
    data = build_tree("World War II", EVENTS[:2], GRAPH, tag_id=1).to_dict()
    assert data["label"] == "World War II" and data["tag"] == 1 and data["count"] == 2
    assert (data["from"], data["to"]) == (1941, 1941)
    leaf = data["children"][0]["children"][0]["children"][0]["children"][0]
    assert leaf == {"label": "Battle of Białystok–Minsk", "count": 1, "qid": "Q10", "event": 1, "year": 1941}
    json.dumps(data)


def test_narrower_tags_from_tag_parents_hang_under_the_root():
    graph = PartOfGraph(parents={"Q1": ["Q50"]}, labels={"Q50": "Peninsular War"},
                        tag_items={"Peninsular War": ["Q50"], "Napoleonic Era": ["Q70"]})
    parents = {"Peninsular War": ["Napoleonic Wars"], "Napoleonic Wars": ["Napoleonic Era"]}
    assert narrower_tags("Napoleonic Era", parents) == {"Napoleonic Wars", "Peninsular War"}
    tree = build_tree("Napoleonic Era", [TreeEvent(1, "Q1", "Battle of Talavera", 1809)], graph,
                      tag_ids={"Peninsular War": 9}, parents=parents)
    assert labels(tree) == ["Peninsular War"]
    assert tree.children[0].tag_id == 9 and labels(tree.children[0]) == ["Battle of Talavera"]


def test_a_tag_without_items_lists_its_events_flat():
    tree = build_tree("Unknown tag", EVENTS[:3], PartOfGraph())
    assert tree.count == 3 and all(not c.children for c in tree.children)


def test_build_graph_keeps_chains_labels_and_tag_items():
    client = FakeClient({
        "E1": ("Battle of Kiev", [], ["Q4"]),
        "Q4": ("Operation Barbarossa", [], ["Q362"]),
        "Q362": ("World War II", ["Second World War"], []),
    })
    graph = build_graph(client, ["E1"], ["World War II"], report=lambda _: None)
    assert graph.parents == {"E1": ["Q4"], "Q4": ["Q362"]}
    assert graph.labels["Q4"] == "Operation Barbarossa"
    assert graph.tag_items == {"World War II": ["Q362"]}


def test_committed_graph_knows_world_war_ii():
    graph = load_graph()
    assert graph.tag_items.get("World War II")
    assert "Operation Barbarossa" in graph.labels.values()


def test_tree_api(client, make_event):
    war = Tag.query.filter_by(name="World War II").one()
    barbarossa = next(q for q, label in load_graph().labels.items() if label == "Operation Barbarossa")
    make_event("Battle in Barbarossa", year=1941, wikidata_id="Q-test-1", tags=[war])
    make_event("Pending battle", year=1941, status=Status.PENDING, tags=[war])
    graph = load_graph()
    graph.parents["Q-test-1"] = [barbarossa]
    try:
        data = client.get(f"/api/tags/{war.id}/tree").get_json()
    finally:
        del graph.parents["Q-test-1"]
    assert data["label"] == "World War II" and data["count"] == 1 and data["tag"] == war.id

    def path(node):
        return [node["label"]] + (path(node["children"][0]) if node.get("children") else [])

    assert path(data)[-2:] == ["Operation Barbarossa", "Battle in Barbarossa"]
    assert client.get("/api/tags/999999/tree").status_code == 404
