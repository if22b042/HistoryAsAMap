"""A tag as a tree of its parts: World War II › Eastern Front › Operation Barbarossa › battles.

The tree is built from Wikidata's "part of" (P361) links, the same links tagging
follows (haam.tagging). They are fetched once, offline, by
``flask --app haam haam build-part-of`` into ``haam/data/part_of.json``:

* ``parents``: item → the items it is directly part of, for every tagged event and
  every item on its chain (up to tagging's MAX_DEPTH, NO_CLIMB items have none);
* ``labels``: item → English label;
* ``tag_items``: tag name → the items whose label or alias is that name (how
  tagging recognises a tag on a chain).

At request time :func:`build_tree` places each event tagged with the tag under
the most specific chain that leads to the tag: for every item it keeps the one
parent that gives the *longest* path to the tag (Battle of Kiev is part of both
Operation Barbarossa and World War II; it goes under Barbarossa). Because every
item keeps a single parent, the result is a tree and an event is counted once.
Events whose chain does not reach one of the tag's items (tags implied by
TAG_PARENTS, or tagged by hand) hang directly under the tag.
Every level is sorted by the number of events in the branch, largest first.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from haam.tagging import MAX_DEPTH, P_PART_OF, TAG_PARENTS, ChainResolver, TagMatcher, normalise

GRAPH_PATH = Path(__file__).parent / "data" / "part_of.json"


@dataclass
class PartOfGraph:
    parents: dict[str, list[str]] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    tag_items: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "PartOfGraph":
        return cls(parents=data.get("parents", {}), labels=data.get("labels", {}),
                   tag_items=data.get("tag_items", {}))

    def to_dict(self) -> dict:
        return {"parents": dict(sorted(self.parents.items())), "labels": dict(sorted(self.labels.items())),
                "tag_items": dict(sorted(self.tag_items.items()))}


@lru_cache(maxsize=1)
def load_graph(path: str | None = None) -> PartOfGraph:
    """The committed graph (empty when the file has not been generated)."""
    file = Path(path) if path else GRAPH_PATH
    if not file.exists():
        return PartOfGraph()
    with open(file, encoding="utf-8") as handle:
        return PartOfGraph.from_dict(json.load(handle))


# ------------------------------------------------------------ building the graph

def build_graph(client, event_qids: Iterable[str], tag_names: Iterable[str], report=print,
                chunk: int = 2000) -> PartOfGraph:
    """Fetch the "part of" chains of events from Wikidata (offline step, needs the network)."""
    from haam.wikidata import item_ids  # local: haam.wikidata imports haam.tagging

    qids = sorted(set(event_qids))
    resolver = ChainResolver(client)
    direct: dict[str, list[str]] = {}
    for start in range(0, len(qids), chunk):
        part = qids[start:start + chunk]
        entities = client.entities(part)
        part_of = {q: item_ids(entities.get(q, {}).get("claims", {}), P_PART_OF) for q in part}
        resolver.resolve(part_of)  # fills resolver.parents / names / labels up the chains
        direct.update(part_of)
        report(f"  {min(start + chunk, len(qids))}/{len(qids)} events")

    by_key = {normalise(name): name for name in tag_names}
    graph = PartOfGraph()
    for qid, parents in [*resolver.parents.items(), *direct.items()]:
        if parents:
            graph.parents[qid] = list(dict.fromkeys(parents))
    graph.labels = {q: label for q, label in resolver.labels.items()}
    for qid, names in resolver.names.items():
        for tag in sorted({by_key[k] for k in map(normalise, names) if k in by_key}):
            graph.tag_items.setdefault(tag, []).append(qid)
    for items in graph.tag_items.values():
        items.sort()
    return graph


def build_graph_file(client, csv_path: str, out: str | Path = GRAPH_PATH, report=print) -> PartOfGraph:
    """:func:`build_graph` for every tagged event of an exported CSV, written as JSON."""
    import csv

    from haam.data.tags import TAGS

    with open(csv_path, newline="", encoding="utf-8") as handle:
        qids = [row["wikidata_id"] for row in csv.DictReader(handle) if row.get("wikidata_id") and row.get("tags")]
    graph = build_graph(client, qids, [name for name, _, _ in TAGS], report=report)
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(graph.to_dict(), handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    load_graph.cache_clear()
    return graph


# ------------------------------------------------------------ building a tree

@dataclass
class TreeEvent:
    id: int
    qid: str | None
    title: str
    year: int | None = None


@dataclass
class Node:
    label: str
    qid: str | None = None
    event_id: int | None = None  # the node is itself an event with the tag
    year: int | None = None
    tag_id: int | None = None  # the node is (the item of) another tag
    children: list["Node"] = field(default_factory=list)
    count: int = 0  # events with the tag in this branch, the node itself included
    first: int | None = None  # years of the branch's events
    last: int | None = None

    def to_dict(self) -> dict:
        data: dict = {"label": self.label, "count": self.count}
        for key, value in (("qid", self.qid), ("event", self.event_id), ("year", self.year), ("tag", self.tag_id)):
            if value is not None:
                data[key] = value
        if self.children:
            data["from"], data["to"] = self.first, self.last
            data["children"] = [child.to_dict() for child in self.children]
        return data


def narrower_tags(name: str, parents: dict[str, list[str]] = TAG_PARENTS) -> set[str]:
    """Tags that TAG_PARENTS puts under ``name``, directly or further down."""
    found, todo = set(), [name]
    while todo:
        current = todo.pop()
        for child, broader in parents.items():
            if current in broader and child not in found and child != name:
                found.add(child)
                todo.append(child)
    return found


_ROOT = "__root__"


def build_tree(tag_name: str, events: Iterable[TreeEvent], graph: PartOfGraph, *,
               tag_id: int | None = None, tag_ids: dict[str, int] | None = None,
               parents: dict[str, list[str]] = TAG_PARENTS) -> Node:
    """The tree of ``tag_name`` for the events that carry it (see the module docstring)."""
    tag_ids = tag_ids or {}
    events = list(events)
    roots = set(graph.tag_items.get(tag_name, []))
    # Items of narrower tags that Wikidata does not link (Peninsular War under the
    # Napoleonic Wars) hang straight under the root.
    bridged = {q for child in narrower_tags(tag_name, parents) for q in graph.tag_items.get(child, [])} - roots
    tag_of_item = {q: tag_ids[name] for name, items in graph.tag_items.items() if name in tag_ids and name != tag_name
                   for q in items}

    best: dict[str, tuple[int, str] | None] = {}

    def climb(qid: str, stack: set[str]) -> tuple[int, str] | None:
        """(steps to the root, next item up) along the longest path, or None."""
        if qid in roots:
            return 0, _ROOT
        if qid in best:
            return best[qid]
        if qid in stack:
            return None  # a loop in Wikidata
        stack.add(qid)
        choice = (1, _ROOT) if qid in bridged else None
        for parent in graph.parents.get(qid, []):
            up = climb(parent, stack)
            if up is not None and up[0] + 1 <= MAX_DEPTH and (choice is None or up[0] + 1 > choice[0]):
                choice = (up[0] + 1, parent)
        stack.discard(qid)
        best[qid] = choice
        return choice

    root = Node(label=tag_name, tag_id=tag_id)
    nodes: dict[str, Node] = {}
    by_qid = {e.qid: e for e in events if e.qid}

    def node_for(qid: str) -> Node:
        if qid not in nodes:
            event = by_qid.get(qid)
            nodes[qid] = Node(label=event.title if event else graph.labels.get(qid, qid), qid=qid,
                              tag_id=tag_of_item.get(qid))
        return nodes[qid]

    def attach(qid: str) -> Node:
        """The node of ``qid``, linked into the tree with all its ancestors."""
        known = qid in nodes
        node = node_for(qid)
        if known:
            return node
        up = climb(qid, set()) if qid not in roots else None
        parent = root if up is None or up[1] == _ROOT or up[1] in roots else attach(up[1])
        parent.children.append(node)
        return node

    for event in events:
        if event.qid:
            node = attach(event.qid)
        else:
            node = Node(label=event.title)
            root.children.append(node)
        node.event_id, node.year, node.label = event.id, event.year, event.title

    _count_and_sort(root)
    return root


def _count_and_sort(node: Node) -> int:
    """Counts and year spans bottom-up; children largest first, then oldest, then by name."""
    for child in node.children:
        _count_and_sort(child)
    node.children = [c for c in node.children if c.count]
    node.children.sort(key=lambda c: (-c.count, c.first if c.first is not None else 10**6, c.label.casefold()))
    node.count = (node.event_id is not None) + sum(c.count for c in node.children)
    years = [y for c in node.children for y in (c.first, c.last) if y is not None]
    if node.event_id is not None and node.year is not None:
        years.append(node.year)
    node.first, node.last = (min(years), max(years)) if years else (None, None)
    return node.count


# ------------------------------------------------------------ from the database

def tag_tree(tag) -> dict:
    """The JSON tree of a Tag, for the approved events that carry it."""
    from sqlalchemy import select

    from haam.extensions import db
    from haam.models import Event, Status, Tag, event_tags

    rows = db.session.execute(
        select(Event.id, Event.wikidata_id, Event.title, Event.year)
        .join(event_tags, event_tags.c.event_id == Event.id)
        .where(event_tags.c.tag_id == tag.id, Event.status == Status.APPROVED)
    ).all()
    tag_ids = dict(db.session.execute(select(Tag.name, Tag.id)).all())
    events = [TreeEvent(id=r.id, qid=r.wikidata_id, title=r.title, year=r.year) for r in rows]
    tree = build_tree(tag.name, events, load_graph(), tag_id=tag.id, tag_ids=tag_ids)
    return tree.to_dict()
