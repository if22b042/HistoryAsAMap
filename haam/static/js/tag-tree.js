// A tag as a tree of its parts (World War II › Eastern Front › Operation Barbarossa
// › battles), in a dialog over the map. The tree comes from /api/tags/<id>/tree
// (haam/tag_tree.py): every node has a label and the number of events in its
// branch; every level is already sorted largest branch first. Levels open on
// demand and long levels show the biggest branches first, the rest behind
// "N more". Picking a node calls onPick(node, root) – the map then filters to it.
// Text from the data only ever goes into textContent.

import { formatYear } from "./events-data.js";

const FIRST_SHOWN = 8; // children shown when a level opens
const MORE_STEP = 25; // shown per click on "N more"
const AUTO_OPEN = 0.9; // a branch with this share of its parent's events opens with it
const cache = new Map(); // tag id -> Promise of the tree

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

const plural = (n, word) => `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;

/** The tree of a tag, fetched once per page. */
export function fetchTagTree(tagId) {
  if (!cache.has(tagId)) {
    const promise = fetch(`/api/tags/${encodeURIComponent(tagId)}/tree`, { headers: { Accept: "application/json" } })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      });
    promise.catch(() => cache.delete(tagId)); // try again next time
    cache.set(tagId, promise);
  }
  return cache.get(tagId);
}

/** Every event id in a branch (the node's own event included). */
export function branchEventIds(node, ids = new Set()) {
  if (node.event !== undefined) ids.add(node.event);
  (node.children || []).forEach((child) => branchEventIds(child, ids));
  return ids;
}

/** The node with Wikidata id ``qid`` (null when the tree has none). */
export function findNode(node, qid) {
  if (node.qid === qid) return node;
  for (const child of node.children || []) {
    const hit = findNode(child, qid);
    if (hit) return hit;
  }
  return null;
}

/** Labels from the root down to the node with ``qid`` ("World War II", "Eastern Front", …). */
export function pathTo(node, qid, path = []) {
  const here = [...path, node.label];
  if (node.qid === qid) return here;
  for (const child of node.children || []) {
    const hit = pathTo(child, qid, here);
    if (hit) return hit;
  }
  return null;
}

/**
 * The dialog. ``createTagTree({ onPick })`` returns ``open(tag)``; the dialog
 * element is #tag-tree in map.html.
 */
export function createTagTree({ onPick }) {
  const dialog = document.getElementById("tag-tree");
  if (!dialog) return { open() {} };
  const title = dialog.querySelector("[data-tree-title]");
  const summary = dialog.querySelector("[data-tree-summary]");
  const body = dialog.querySelector("[data-tree-body]");
  let request = 0;

  dialog.querySelector("[data-tree-close]").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); }); // the backdrop
  dialog.addEventListener("keydown", (e) => { if (e.key === "Escape") e.stopPropagation(); });

  function pick(node, root) {
    dialog.close();
    onPick(node, root);
  }

  /** One row: open/close toggle, the name (a button that filters the map), count and bar. */
  function row(node, root, parentCount, depth) {
    const item = el("li", "tree-node");
    item.setAttribute("role", "treeitem");
    item.setAttribute("aria-level", String(depth));
    const line = el("div", "tree-line");
    const hasChildren = Boolean(node.children && node.children.length);
    const toggle = el("button", "tree-toggle");
    toggle.type = "button";
    if (hasChildren) {
      toggle.setAttribute("aria-label", `Show the parts of ${node.label}`);
      toggle.setAttribute("aria-expanded", "false");
      item.setAttribute("aria-expanded", "false");
    } else {
      toggle.disabled = true;
      toggle.setAttribute("aria-hidden", "true");
      toggle.tabIndex = -1;
    }
    const name = el("button", "tree-name");
    name.type = "button";
    name.append(el("span", "tree-label", node.label));
    if (node.tag !== undefined && node.tag !== root.tag) name.append(el("span", "tree-badge", "tag"));
    if (!hasChildren && node.year !== undefined) name.append(el("span", "tree-year", formatYear(node.year)));
    if (hasChildren && node.from !== undefined && node.from !== null) {
      const span = node.from === node.to ? formatYear(node.from) : `${formatYear(node.from)}–${formatYear(node.to)}`;
      name.append(el("span", "tree-year", span));
    }
    name.title = hasChildren || node.event === undefined
      ? `Show the ${plural(node.count, "event")} of ${node.label} on the map`
      : `Open ${node.label}`;
    name.addEventListener("click", () => pick(node, root));
    const count = el("span", "tree-count", node.count.toLocaleString());
    count.setAttribute("aria-label", plural(node.count, "event"));
    const bar = el("span", "tree-bar");
    const fill = el("span");
    fill.style.width = `${Math.max(2, Math.round((100 * node.count) / Math.max(1, parentCount)))}%`;
    bar.append(fill);
    bar.setAttribute("aria-hidden", "true");
    line.append(toggle, name, count, bar);
    item.append(line);

    if (hasChildren) {
      let list = null;
      const setOpen = (open) => {
        if (open && !list) {
          list = childList(node, root, depth + 1);
          item.append(list);
        }
        if (list) list.hidden = !open;
        toggle.setAttribute("aria-expanded", String(open));
        item.setAttribute("aria-expanded", String(open));
        toggle.setAttribute("aria-label", `${open ? "Hide" : "Show"} the parts of ${node.label}`);
      };
      toggle.addEventListener("click", () => setOpen(toggle.getAttribute("aria-expanded") !== "true"));
      item.setOpen = setOpen;
      // A level that is almost all one branch (Eastern European theatre: 132 of its 133
      // events are the Eastern Front) opens on its own, so chains need fewer clicks.
      const [largest] = node.children;
      if (depth > 1 && largest.children && largest.count >= AUTO_OPEN * node.count) queueMicrotask(() => setOpen(true));
    }
    return item;
  }

  /** The children of a node: the largest first, the rest behind "N more". */
  function childList(node, root, depth) {
    const list = el("ul", "tree-children");
    list.setAttribute("role", "group");
    const children = node.children || [];
    let shown = 0;
    const more = el("li", "tree-more");
    const moreButton = el("button", "tree-more-btn");
    moreButton.type = "button";
    more.append(moreButton);
    const showMore = (n) => {
      const next = children.slice(shown, shown + n);
      next.forEach((child) => list.insertBefore(row(child, root, node.count, depth), more));
      shown += next.length;
      const left = children.slice(shown);
      more.hidden = left.length === 0;
      if (left.length) {
        const events = left.reduce((sum, child) => sum + child.count, 0);
        moreButton.textContent = left.length === events
          ? `${plural(left.length, "more event")}`
          : `${left.length.toLocaleString()} more (${plural(events, "event")})`;
      }
    };
    list.append(more);
    moreButton.addEventListener("click", () => {
      const before = shown;
      showMore(MORE_STEP);
      list.children[before]?.querySelector(".tree-name")?.focus();
    });
    showMore(FIRST_SHOWN);
    return list;
  }

  function render(root) {
    title.textContent = `Parts of ${root.label}`;
    const parts = (root.children || []).filter((c) => c.children).length;
    summary.textContent = `${plural(root.count, "event")} · ${plural(parts, "part")} with events of their own · `
      + "largest first. Click a name to show it on the map.";
    const tree = el("ul", "tree");
    tree.setAttribute("role", "tree");
    tree.setAttribute("aria-labelledby", title.id);
    const top = row(root, root, root.count, 1);
    top.classList.add("tree-root");
    tree.append(top);
    body.replaceChildren(tree);
    top.setOpen?.(true);
  }

  async function open(tag) {
    const mine = ++request;
    title.textContent = `Parts of ${tag.name}`;
    summary.textContent = "Loading…";
    body.replaceChildren();
    if (!dialog.open) dialog.showModal();
    try {
      const root = await fetchTagTree(tag.id);
      if (mine === request) render(root);
    } catch {
      if (mine === request) summary.textContent = "The tree could not be loaded. Please try again.";
    }
  }

  return { open };
}

