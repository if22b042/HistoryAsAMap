// "Add to collection" on the main map: a button in the details panel (and a small
// one on each big-search result) listing the collections this browser may edit.
// The list comes from /collections/mine.json; adding is a JSON POST with the CSRF
// token in the X-CSRFToken header. Every control on the page is redrawn after a
// change, so the panel and the search results always agree.

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function icon(name) {
  const i = el("i", `fas fa-${name}`);
  i.setAttribute("aria-hidden", "true");
  return i;
}

let menuCount = 0;

/** Scroll the nearest scrolling box (panel, result list) to show ``node`` – never the page. */
function reveal(node) {
  let box = node.parentElement;
  while (box && !/(auto|scroll)/.test(getComputedStyle(box).overflowY)) box = box.parentElement;
  if (!box || box === document.documentElement || box === document.body) return;
  const below = node.getBoundingClientRect().bottom - box.getBoundingClientRect().bottom;
  if (below > 0) box.scrollTop += below + 8;
}

/** @param {string|undefined} url  /collections/mine.json, or nothing (collection maps) */
export function createCollectionAdder(url) {
  let data = null; // {csrf_token, new_url, collections: [{title, url, add_url, event_ids}]}
  const live = new Set(); // the controls on the page: {box, render, close}

  function prune() {
    live.forEach((c) => { if (!c.box.isConnected) live.delete(c); });
  }

  function redrawAll() {
    prune();
    live.forEach((c) => c.render());
  }

  // A click anywhere else closes an open menu (clicks inside a control stop here).
  if (url) document.addEventListener("click", () => live.forEach((c) => c.close()));

  async function load() {
    if (!url) return;
    try {
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`${url} returned ${response.status}`);
      data = await response.json();
      data.collections.forEach((c) => { c.event_ids = new Set(c.event_ids); });
    } catch (error) {
      console.error(error);
      data = { csrf_token: null, new_url: "/collections/new", collections: [], failed: true };
    }
    redrawAll();
  }

  const containing = (eventId) => (data ? data.collections.filter((c) => c.event_ids.has(eventId)) : []);

  async function add(collection, eventId) {
    let response;
    let body = {};
    try {
      response = await fetch(collection.add_url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": data.csrf_token || "" },
        body: JSON.stringify({ event_id: eventId }),
      });
      body = await response.json().catch(() => ({}));
    } catch (error) {
      console.error(error);
      return { ok: false, message: "Could not reach the server. Please try again." };
    }
    if (response.ok) {
      collection.event_ids = new Set(body.collection.event_ids);
      // The collection just changed: it goes to the top, like on the collections page.
      data.collections = [collection, ...data.collections.filter((c) => c !== collection)];
      return { ok: true, message: body.message };
    }
    if (response.status === 409) collection.event_ids.add(eventId);
    if (response.status === 403) data.collections = data.collections.filter((c) => c !== collection);
    return { ok: false, message: body.error || "Could not add the event. Reload the page and try again." };
  }

  /** The control for one event, or null on pages without it. ``compact``: an icon for search results. */
  function control(eventId, { compact = false } = {}) {
    if (!url) return null;
    const box = el("div", compact ? "collection-add collection-add-compact" : "collection-add");
    const menuId = `collection-menu-${++menuCount}`;
    let open = false;
    let status = null; // {ok, message} after the last attempt

    function setOpen(value, { focus = false } = {}) {
      open = value;
      render();
      if (focus) {
        const target = open ? box.querySelector(".collection-menu-item:not([disabled])") : box.querySelector(".collection-add-toggle");
        if (target) target.focus({ preventScroll: true });
      }
      if (open) reveal(box.querySelector(".collection-menu"));
    }

    function toggleButton(inCollections) {
      const button = el("button", compact ? "icon-btn collection-add-toggle" : "btn btn-secondary collection-add-toggle");
      button.type = "button";
      button.setAttribute("aria-expanded", String(open));
      button.setAttribute("aria-controls", menuId);
      if (compact) {
        const label = inCollections.length
          ? `In ${inCollections.map((c) => `“${c.title}”`).join(", ")} – add to another collection`
          : "Add to collection";
        button.title = label;
        button.setAttribute("aria-label", label);
        button.append(icon(inCollections.length ? "check" : "plus"));
        if (inCollections.length) button.classList.add("is-in");
      } else {
        button.append(icon("layer-group"), " Add to collection ", icon(open ? "caret-up" : "caret-down"));
      }
      button.addEventListener("click", (e) => {
        e.stopPropagation();
        setOpen(!open, { focus: true });
      });
      return button;
    }

    function menu() {
      const list = el("div", "collection-menu");
      list.id = menuId;
      if (!data) {
        list.append(el("p", "collection-menu-label", "Loading your collections…"));
        return list;
      }
      if (data.collections.length) {
        list.append(el("p", "collection-menu-label", "Your collections"));
        data.collections.forEach((collection) => {
          const item = el("button", "collection-menu-item");
          item.type = "button";
          const already = collection.event_ids.has(eventId);
          item.append(icon(already ? "check" : "plus"), el("span", null, collection.title));
          if (already) {
            item.disabled = true;
            item.append(el("span", "collection-menu-note", "already in"));
          }
          item.addEventListener("click", async (e) => {
            e.stopPropagation();
            item.disabled = true;
            status = await add(collection, eventId);
            open = !status.ok;
            redrawAll();
            const toggle = box.querySelector(".collection-add-toggle");
            if (toggle && status.ok) toggle.focus({ preventScroll: true });
          });
          list.append(item);
        });
      } else {
        list.append(el("p", "collection-menu-label",
          data.failed ? "Could not load your collections." : "This browser has no collections to edit yet."));
      }
      const create = el("a", "collection-menu-item collection-menu-new");
      create.href = `${data.new_url}?event=${eventId}`;
      create.append(icon("folder-plus"), el("span", null, "New collection with this event"));
      list.append(create);
      return list;
    }

    function inLine(inCollections) {
      const line = el("p", "collection-in");
      line.append(icon("layer-group"), " In: ");
      inCollections.forEach((collection, i) => {
        if (i) line.append(", ");
        const link = el("a", null, collection.title);
        link.href = collection.url;
        line.append(link);
      });
      return line;
    }

    function render() {
      const inCollections = containing(eventId);
      const parts = [toggleButton(inCollections)];
      if (open) parts.push(menu());
      if (!compact && inCollections.length) parts.push(inLine(inCollections));
      const message = el("p", `collection-add-status${status && !status.ok ? " is-error" : ""}`, status ? status.message : "");
      message.setAttribute("role", "status");
      if (!compact || (status && !status.ok)) parts.push(message);
      box.replaceChildren(...parts);
      if (compact) box.classList.toggle("is-open", open);
    }

    box.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && open) {
        e.preventDefault();
        e.stopPropagation(); // do not also close the search panel
        setOpen(false, { focus: true });
      }
    });
    box.addEventListener("click", (e) => e.stopPropagation());

    prune();
    live.add({ box, render, close: () => { if (open) setOpen(false); } });
    render();
    return box;
  }

  return { load, control };
}
