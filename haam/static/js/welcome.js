// The map's welcome card: what the site is, "On this day", today's game and
// featured collections. It opens by itself on the first visit only; the "Today"
// button reopens it and shows a dot on a new day. Data comes from one small
// request, made only when the card opens, so it never delays the map.

const card = document.getElementById("welcome");
const openButton = document.getElementById("welcome-open");
const SEEN_KEY = "haam.welcome.seen"; // the visitor's last local day with the card seen

function localDay(date = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function readSeen() {
  try { return localStorage.getItem(SEEN_KEY); } catch { return null; }
}

function markSeen() {
  try { localStorage.setItem(SEEN_KEY, localDay()); } catch { /* storage blocked: shown again next visit */ }
  document.getElementById("welcome-dot").hidden = true;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function eventItem(event) {
  const item = el("li");
  const button = el("button", "welcome-event");
  button.type = "button";
  button.title = event.excerpt;
  button.append(
    el("span", "welcome-event-year", event.display_year),
    el("span", `dot dot-${event.category}`),
    el("span", "welcome-event-title", event.title),
  );
  button.addEventListener("click", () => {
    close({ restoreFocus: false });
    document.dispatchEvent(new CustomEvent("haam:show-event", { detail: { id: event.id } }));
  });
  item.append(button);
  return item;
}

function collectionItem(collection) {
  const item = el("li");
  const link = el("a", "welcome-collection");
  link.href = collection.url;
  const count = `${collection.entries} ${collection.entries === 1 ? "entry" : "entries"}`;
  link.append(el("strong", null, collection.title),
    el("span", null, collection.years ? `${count} · ${collection.years}` : count));
  item.append(link);
  return item;
}

let loadedFor = null;

async function load() {
  const now = new Date();
  const day = localDay(now);
  if (loadedFor === day) return;
  loadedFor = day;
  const list = document.getElementById("welcome-events");
  // The visitor's own calendar day, not the server's.
  const url = `${card.dataset.url}?month=${now.getMonth() + 1}&day=${now.getDate()}`;
  let data;
  try {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`${response.status} ${url}`);
    data = await response.json();
  } catch (error) {
    console.error(error);
    loadedFor = null;
    list.replaceChildren(el("li", "welcome-empty", "Could not load today's events."));
    return;
  }

  document.getElementById("welcome-day").textContent = ` · ${data.day_label}`;
  list.replaceChildren(...(data.on_this_day.length
    ? data.on_this_day.map(eventItem)
    : [el("li", "welcome-empty", "No events recorded for this day yet.")]));

  if (data.game) document.getElementById("welcome-game-number").textContent = ` #${data.game.number}`;

  document.getElementById("welcome-collections-box").hidden = !data.collections.length;
  document.getElementById("welcome-collections").replaceChildren(...data.collections.map(collectionItem));
}

let returnFocus = null;

function open({ first = false } = {}) {
  document.getElementById("welcome-title").textContent =
    first ? "Welcome to History As A Map" : "Today in history";
  returnFocus = first ? null : document.activeElement;
  card.hidden = false;
  openButton.setAttribute("aria-expanded", "true");
  document.body.classList.add("welcome-shown");
  card.focus({ preventScroll: true });
  markSeen();
  load();
}

function close({ restoreFocus = true } = {}) {
  if (card.hidden) return;
  const hadFocus = card.contains(document.activeElement);
  card.hidden = true;
  openButton.setAttribute("aria-expanded", "false");
  document.body.classList.remove("welcome-shown");
  if (restoreFocus && hadFocus) {
    const target = returnFocus && returnFocus !== document.body && document.contains(returnFocus)
      && !returnFocus.closest("[hidden]") ? returnFocus : openButton;
    target.focus({ preventScroll: true });
  }
  returnFocus = null;
}

if (card && openButton) {
  openButton.addEventListener("click", () => (card.hidden ? open() : close()));
  document.getElementById("welcome-close").addEventListener("click", () => close());

  // Capture phase: runs before the map's own Escape handler (which closes the details panel).
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || card.hidden || e.defaultPrevented) return;
    if (document.getElementById("search-panel")?.hidden === false) return; // the search closes first
    e.preventDefault();
    close();
  }, true);

  // The card and the event details share one place: opening an event closes the card.
  new MutationObserver(() => {
    if (document.body.classList.contains("sidebar-open")) close({ restoreFocus: false });
  }).observe(document.body, { attributes: true, attributeFilter: ["class"] });

  // A shared link to one event goes straight to it; the card waits for a later visit.
  const linkedEvent = new URLSearchParams(window.location.search).has("event");
  const seen = readSeen();
  if (!seen && !linkedEvent) open({ first: true });
  else if (seen !== localDay()) document.getElementById("welcome-dot").hidden = false;
}
