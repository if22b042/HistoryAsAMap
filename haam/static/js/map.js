// Map page: loads approved events from the API, shows them as clustered markers
// (or a heatmap), filters by year/category/tag/text and lists them below the map.
// The events arrive in chunks (see events-data.js): the first one is drawn at
// once and the others are added as they come in; everything works meanwhile.
/* global L, noUiSlider */
import { createCollectionAdder } from "./collection-add.js";
import { createTimeline } from "./timeline.js";
import { chunkOrder, compareEvents, decodeCore, formatYear, getJson, getJsonRetry, mergeSorted } from "./events-data.js";

// Map zoom when an event is picked in the search or on the timeline: 9 is twice
// the scale of the earlier 8 (each zoom level doubles it), about a city.
const CLICK_ZOOM = 9;

const CATEGORY_LABELS = {
  military: "Military",
  diplomatic: "Diplomatic",
  naval: "Naval",
  scientific: "Scientific",
  natural: "Natural",
  other: "Other",
};

const state = {
  events: [], // loaded so far, sorted by year and title
  total: 0, // events on the map once every chunk has arrived
  loading: false, // chunks still on their way
  textsLoading: false, // the short descriptions are still on their way
  eventsById: new Map(),
  markersById: new Map(),
  tagsById: new Map(),
  filtered: [],
  yearFrom: -Infinity,
  yearTo: Infinity,
  category: "all",
  tagIds: [], // selected tags (see "tags" below)
  tagMode: "any", // an event needs "any" or "all" of them
  tagCounts: new Map(), // tag id -> events matching the other filters
  query: "",
  heatmap: false,
  colorByYear: false,
  // Years the colour scale spans: the earliest and latest event currently shown.
  colorFrom: 0,
  colorTo: 0,
  openId: null,
};

// ------------------------------------------------------------ year colours

// The scale runs once through the spectrum: red (earliest) → violet (latest).
const HUE_SPAN = 280;

function hueForYear(year) {
  const span = state.colorTo - state.colorFrom;
  if (span <= 0) return 0;
  const t = Math.min(1, Math.max(0, (year - state.colorFrom) / span));
  return Math.round(t * HUE_SPAN);
}

const yearColor = (year) => `hsl(${hueForYear(year)} 85% 45%)`;
const hueColor = (hue) => `hsl(${hue} 85% 45%)`;

/** In colour mode a year label gets its year's colour, so the list matches the map. */
function paintYearPill(pill, year) {
  pill.classList.toggle("year-pill-colored", state.colorByYear);
  pill.style.background = state.colorByYear ? yearColor(year) : "";
}

// ------------------------------------------------------------------ helpers

/** Create an element with optional class and text (never parses HTML). */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function safeWikipediaUrl(url) {
  return /^https:\/\/en\.wikipedia\.org\/wiki\//.test(url) ? url : null;
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// ---------------------------------------------------------------------- map

const map = L.map("map", {
  center: [30, 10],
  zoom: 3,
  minZoom: 2,
  maxZoom: 18,
  worldCopyJump: true,
  maxBounds: [[-90, -200], [90, 200]],
  maxBoundsViscosity: 0.8,
  zoomControl: false, // re-added bottom-right so the filter panel doesn't cover it
});
L.control.zoom({ position: "bottomright" }).addTo(map);

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 18,
}).addTo(map);

const clusters = L.markerClusterGroup({
  showCoverageOnHover: false,
  maxClusterRadius: 45,
  spiderfyOnMaxZoom: true,
  chunkedLoading: true,
  iconCreateFunction(cluster) {
    const count = cluster.getChildCount();
    const size = count < 10 ? "small" : count < 100 ? "medium" : "large";
    if (state.colorByYear) {
      // A cluster takes the colour of the average year of the events in it.
      const markers = cluster.getAllChildMarkers();
      const mean = markers.reduce((sum, m) => sum + m.options.year, 0) / markers.length;
      return L.divIcon({
        // Only numbers we computed go into this HTML – safe.
        html: `<span class="cluster-year-fill" style="background:${yearColor(mean)}">${count}</span>`,
        className: `cluster cluster-year cluster-${size}`,
        iconSize: L.point(40, 40),
      });
    }
    // All events of one category: the cluster takes that category's colour.
    // Mixed clusters keep the default colour (which matches no category).
    const markers = cluster.getAllChildMarkers();
    const category = markers[0].options.category;
    const single = markers.every((m) => m.options.category === category);
    const catClass = single ? ` cluster-cat cluster-cat-${category}` : "";
    return L.divIcon({
      html: `<span>${count}</span>`, // a number we computed – safe
      className: `cluster cluster-${size}${catClass}`,
      iconSize: L.point(40, 40),
    });
  },
}).addTo(map);

let heatLayer = null;

// The heatmap has no markers, so a click looks for events right under the pointer:
// one opens it, several close together zoom in, none does nothing.
const HEAT_CLICK_RADIUS = 14; // px
map.on("click", (e) => {
  if (!state.heatmap) return;
  const hits = [];
  state.filtered.forEach((event) => {
    const distance = map.latLngToContainerPoint([event.lat, event.lon]).distanceTo(e.containerPoint);
    if (distance <= HEAT_CLICK_RADIUS) hits.push({ event, distance });
  });
  if (!hits.length) return;
  hits.sort((a, b) => a.distance - b.distance);
  const sameSpot = hits.every((h) => h.event.lat === hits[0].event.lat && h.event.lon === hits[0].event.lon);
  if (hits.length === 1 || sameSpot || map.getZoom() >= map.getMaxZoom()) {
    showEvent(hits[0].event.id, { zoom: map.getZoom() });
  } else {
    map.flyTo(e.latlng, Math.min(map.getZoom() + 2, map.getMaxZoom()), { duration: 0.6 });
  }
});

// …and the pointer becomes a hand over a spot where clicking does something.
let heatHover = 0;
map.on("mousemove", (e) => {
  if (!state.heatmap || heatHover) return;
  heatHover = requestAnimationFrame(() => {
    heatHover = 0;
    const near = state.filtered.some((event) =>
      map.latLngToContainerPoint([event.lat, event.lon]).distanceTo(e.containerPoint) <= HEAT_CLICK_RADIUS);
    map.getContainer().classList.toggle("heat-clickable", near);
  });
});

// Pop-out timeline of the events shown (only while there are few of them).
const timeline = createTimeline({
  map,
  limit: 1000, // crowded labels turn into dots, so the timeline stays readable
  onSelect: (id) => showEvent(id, { zoom: CLICK_ZOOM }),
  colorFor: (item) => (state.colorByYear ? yearColor(item.year) : null),
});

const MARKER_ICON = { iconSize: [18, 18], iconAnchor: [9, 9], popupAnchor: [0, -9] };
const categoryIcons = new Map();
const hueIcons = new Map(); // at most HUE_SPAN + 1 icons, shared by all markers

function markerIcon(category) {
  if (!categoryIcons.has(category)) {
    categoryIcons.set(category, L.divIcon({ className: `marker marker-${category}`, ...MARKER_ICON }));
  }
  return categoryIcons.get(category);
}

function yearIcon(year) {
  const hue = hueForYear(year);
  if (!hueIcons.has(hue)) {
    hueIcons.set(hue, L.divIcon({
      className: "marker marker-year",
      html: `<span class="marker-year-fill" style="background:${hueColor(hue)}"></span>`,
      ...MARKER_ICON,
    }));
  }
  return hueIcons.get(hue);
}

// ------------------------------------------------------------ year legend

// Bottom right, above the zoom buttons: the filter panel covers the left side.
const legend = L.control({ position: "bottomright" });
legend.onAdd = () => {
  const box = el("div", "year-legend");
  box.append(el("span", "year-legend-title", "Colour = year"));
  const bar = el("div", "year-legend-bar");
  const stops = Array.from({ length: 8 }, (_, i) => hueColor(Math.round((i / 7) * HUE_SPAN)));
  bar.style.background = `linear-gradient(to right, ${stops.join(", ")})`;
  box.append(bar, el("div", "year-legend-ticks"), el("span", "year-legend-span"));
  L.DomEvent.disableClickPropagation(box);
  return box;
};

function updateLegend() {
  const box = legend.getContainer();
  if (!box) return;
  const { colorFrom: from, colorTo: to } = state;
  const ticks = box.querySelector(".year-legend-ticks");
  const span = box.querySelector(".year-legend-span");
  if (!state.filtered.length) {
    ticks.replaceChildren(el("span", null, "No events"));
    span.textContent = "";
    return;
  }
  const count = to - from >= 4 ? 5 : to > from ? 2 : 1;
  const values = count === 1 ? [from] : Array.from({ length: count }, (_, i) => Math.round(from + ((to - from) * i) / (count - 1)));
  ticks.replaceChildren(...values.map((year) => {
    const tick = el("span", "year-legend-tick", formatYear(year));
    tick.style.color = yearColor(year);
    return tick;
  }));
  const years = to - from;
  span.textContent = years > 0 ? `${years.toLocaleString()} years, earliest → latest shown` : "All in one year";
}

function updateColorRange() {
  let from = Infinity;
  let to = -Infinity;
  state.filtered.forEach((e) => {
    if (e.year < from) from = e.year;
    if (e.year > to) to = e.year;
  });
  state.colorFrom = Number.isFinite(from) ? from : 0;
  state.colorTo = Number.isFinite(to) ? to : 0;
}

function popupContent(event) {
  const box = el("div", "popup");
  box.append(el("strong", "popup-title", event.title));
  box.append(el("span", "popup-year", event.date || event.display_year));
  if (event.excerpt) box.append(el("p", "popup-summary", event.excerpt));
  const button = el("button", "popup-btn", "View details →");
  button.type = "button";
  button.addEventListener("click", () => showEvent(event.id));
  box.append(button);
  return box;
}

function createMarker(event) {
  return L.marker([event.lat, event.lon], { icon: markerIcon(event.category), title: event.title, year: event.year, category: event.category })
    .bindPopup(() => popupContent(event), { maxWidth: 300 });
}

// ------------------------------------------------------------------ sidebar

const sidebar = document.getElementById("sidebar");
const sidebarContent = document.getElementById("sidebar-content");

const detailsCache = new Map();

// The data this page shows: every approved event, or one collection's entries
// (whose list already carries the full text, so no details are fetched).
const MAP_ELEMENT = document.getElementById("map");
const EVENTS_URL = MAP_ELEMENT.dataset.eventsUrl || "/api/events";
const FULL_TEXT = MAP_ELEMENT.dataset.fullText === "1";
// "Add to collection": only on the main map (a collection's map has no URL for it).
const collectionAdder = createCollectionAdder(MAP_ELEMENT.dataset.collectionsUrl);

const safeWebUrl = (url) => (/^https?:\/\//.test(url || "") ? url : null);

async function loadDetails(id) {
  if (FULL_TEXT) {
    const event = state.eventsById.get(id);
    return event ? { summary: event.summary || event.excerpt, country: null } : null;
  }
  if (!detailsCache.has(id)) {
    detailsCache.set(id, getJson(`/api/events/${id}`).catch((error) => {
      console.error(error);
      detailsCache.delete(id);
      return null;
    }));
  }
  return detailsCache.get(id);
}

function showEvent(id, { fly = true, zoom = 6 } = {}) {
  const event = state.eventsById.get(id);
  if (!event) return;

  const parts = [];
  const pill = el("span", "year-pill", event.date || event.display_year);
  paintYearPill(pill, event.year);
  parts.push(pill);
  parts.push(el("h3", "detail-title", event.title));

  const meta = el("p", "detail-meta");
  const badge = el("span", `badge badge-${event.category}`, CATEGORY_LABELS[event.category]);
  meta.append(badge, ` ${event.lat.toFixed(4)}, ${event.lon.toFixed(4)}`);
  const country = el("span");
  meta.append(country);
  parts.push(meta);

  // The list only carries an excerpt; the full text is fetched on demand.
  const summary = el("p", "detail-summary", event.excerpt);
  parts.push(summary);
  loadDetails(id).then((details) => {
    if (!details || state.openId !== id) return;
    summary.textContent = details.summary;
    if (details.country) country.textContent = ` · ${details.country}`;
  });

  if (event.tags.length) {
    const tags = el("p", "tag-list");
    event.tags.forEach((tagId) => {
      const tag = state.tagsById.get(tagId);
      if (tag) tags.append(tagButton(tag));
    });
    parts.push(tags);
  }

  if (event.note) {
    const note = el("div", "detail-note");
    note.append(el("strong", null, "Note from the collection: "), event.note);
    parts.push(note);
  }
  if (event.moved) parts.push(el("p", "form-hint", "Placed at other coordinates in this collection."));

  const actions = el("div", "detail-actions");
  const wiki = safeWikipediaUrl(event.wiki_url);
  if (wiki) {
    const link = el("a", "btn btn-primary", "Read on Wikipedia");
    link.href = wiki;
    link.target = "_blank";
    link.rel = "noopener";
    actions.append(link);
  }
  const source = !wiki && safeWebUrl(event.link);
  if (source) {
    const link = el("a", "btn btn-primary", "Open the source");
    link.href = source;
    link.target = "_blank";
    link.rel = "noopener noreferrer nofollow ugc";
    actions.append(link);
  }
  const maps = el("a", "btn btn-secondary", "Google Maps");
  maps.href = `https://www.google.com/maps?q=${event.lat},${event.lon}`;
  maps.target = "_blank";
  maps.rel = "noopener";
  actions.append(maps);
  if (!FULL_TEXT) {
    // Main-map events have their own page, the link to share or bookmark.
    const page = el("a", "btn btn-secondary", "Event page");
    page.href = `/event/${encodeURIComponent(id)}`;
    actions.append(page);
  }
  parts.push(actions);
  const adder = collectionAdder.control(id);
  if (adder) parts.push(adder);

  const newEvent = state.openId !== id;
  state.openId = id;
  showSelection(event);
  sidebarContent.replaceChildren(...parts);
  const wasHidden = sidebar.hidden;
  sidebar.hidden = false;
  document.body.classList.add("sidebar-open");
  if (isPhone()) {
    setFiltersOpen(false);
    if (newEvent) sidebarContent.scrollTop = 0;
    openSheet(wasHidden);
  }

  const url = new URL(window.location);
  url.searchParams.set("event", id);
  history.replaceState(null, "", url);

  if (fly) {
    map.closePopup();
    flyToVisible([event.lat, event.lon], Math.max(map.getZoom(), zoom), { duration: 0.8 });
  }
  timeline.setActive(id);
}

// The event that is open on the right gets a black-and-white ring (no colour, so it
// never looks like a category or year colour). The ring is drawn on the event's own
// marker, which leaves the cluster group while it is selected: so it is never hidden
// in a cluster and the ring moves exactly with the dot while zooming.
let selectedMarker = null;

function ringOn(marker) {
  const element = marker.getElement();
  if (element) element.classList.add("marker-selected");
}

function showSelection(event) {
  const marker = state.markersById.get(event.id);
  if (!marker) return;
  if (selectedMarker && selectedMarker !== marker) releaseSelection();
  selectedMarker = marker;
  if (clusters.hasLayer(marker)) clusters.removeLayer(marker);
  if (!map.hasLayer(marker)) marker.addTo(map);
  marker.setZIndexOffset(10000);
  ringOn(marker);
}

/** Put the selected marker back where it belongs: into its cluster, if it is still shown. */
function releaseSelection() {
  const marker = selectedMarker;
  if (!marker) return;
  selectedMarker = null;
  marker.getElement()?.classList.remove("marker-selected");
  marker.setZIndexOffset(0);
  map.removeLayer(marker);
  const shown = !state.heatmap && state.filtered.some((e) => state.markersById.get(e.id) === marker);
  if (shown) clusters.addLayer(marker);
}

function closeSidebar() {
  releaseSelection();
  timeline.setActive(null);
  state.openId = null;
  sidebar.hidden = true;
  document.body.classList.remove("sidebar-open");
  resetSheet();
  const url = new URL(window.location);
  url.searchParams.delete("event");
  history.replaceState(null, "", url);
}

document.getElementById("sidebar-close").addEventListener("click", closeSidebar);
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || e.defaultPrevented) return;
  if (isPhone() && document.body.classList.contains("filters-open")) setFiltersOpen(false);
  else if (!sidebar.hidden) closeSidebar();
});

// ------------------------------------------------------------ phone layout
// Up to 860px wide the filters are a drawer over the map and the details a bottom
// sheet: "peek" shows the date and title, "full" the whole text. The sheet has a
// fixed height and slides with a transform; the map flies so the event lands in
// the part of the map the sheet leaves free.

const phoneQuery = window.matchMedia("(max-width: 860px)");
const isPhone = () => phoneQuery.matches;
const FAB_SPACE = 56; // px at the top of the map taken by the floating buttons
const sheet = { state: "closed" }; // "closed" | "peek" | "full"

const sheetHeight = () => sidebar.offsetHeight;

/** Height of the peek: the sheet down to just below the event's title. */
function peekHeight() {
  const title = sidebarContent.querySelector(".detail-title");
  if (!title) return Math.min(120, sheetHeight());
  const below = title.getBoundingClientRect().bottom - sidebar.getBoundingClientRect().top;
  return Math.min(sheetHeight(), Math.round(below + 12));
}

function sheetOffset(stateName) {
  if (stateName === "full") return 0;
  if (stateName === "peek") return sheetHeight() - peekHeight();
  return sheetHeight();
}

function placeSheet(y, animate) {
  sidebar.classList.toggle("sheet-animating", animate);
  sidebar.style.transform = typeof y === "number" ? `translateY(${Math.round(y)}px)` : `translateY(${y})`;
}

// Relative to the sheet's own height, which grows when the full text arrives.
const SHEET_POSITION = { full: "0px", peek: () => `calc(100% - ${peekHeight()}px)`, closed: "100%" };

function setSheet(stateName, { animate = true } = {}) {
  sheet.state = stateName;
  sidebar.classList.toggle("sheet-peek", stateName === "peek");
  const position = SHEET_POSITION[stateName];
  placeSheet(typeof position === "function" ? position() : position, animate);
  // The zoom buttons and the timeline move up above the peek.
  MAP_ELEMENT.style.setProperty("--sheet-covered", `${peekHeight()}px`);
}

/** Show the sheet for a newly shown event: slide in to the peek, or keep its state. */
function openSheet(fromClosed) {
  if (fromClosed || sheet.state === "closed") {
    placeSheet("100%", false);
    void sidebar.offsetHeight; // start the slide from below the screen
    setSheet("peek");
  } else {
    setSheet(sheet.state, { animate: false });
  }
}

function resetSheet() {
  sheet.state = "closed";
  sidebar.classList.remove("sheet-peek", "sheet-animating");
  sidebar.style.transform = "";
  MAP_ELEMENT.style.removeProperty("--sheet-covered");
}

/** Pixels at the bottom of the map hidden by the sheet or the filter drawer. */
function coveredBottom() {
  if (!isPhone()) return 0;
  let visible = 0;
  if (!sidebar.hidden && sheet.state !== "closed") visible = sheet.state === "full" ? sheetHeight() : peekHeight();
  if (document.body.classList.contains("filters-open")) {
    visible = Math.max(visible, document.getElementById("filters").offsetHeight);
  }
  const rect = MAP_ELEMENT.getBoundingClientRect();
  const covered = rect.bottom - (window.innerHeight - visible);
  return Math.max(0, Math.min(covered, rect.height - FAB_SPACE - 40));
}

/** flyTo, but on a phone the target lands in the middle of the part of the map that is free. */
function flyToVisible(latlng, zoom, options) {
  const shift = isPhone() ? (coveredBottom() - FAB_SPACE) / 2 : 0;
  if (!shift) {
    map.flyTo(latlng, zoom, options);
    return;
  }
  const point = map.project(latlng, zoom).add([0, shift]);
  map.flyTo(map.unproject(point, zoom), zoom, options);
}

/** After the sheet changed size: pan, if needed, so the open event stays in sight. */
function keepOpenEventVisible() {
  const event = state.openId !== null && state.eventsById.get(state.openId);
  if (!event) return;
  const point = map.latLngToContainerPoint([event.lat, event.lon]);
  const bottom = MAP_ELEMENT.clientHeight - coveredBottom();
  if (point.y >= FAB_SPACE && point.y <= bottom - 24) return;
  map.panBy([0, point.y - (FAB_SPACE + bottom) / 2], { duration: 0.3 });
}

function changeSheet(stateName) {
  if (stateName === "closed") {
    const closing = state.openId;
    placeSheet("100%", true);
    setTimeout(() => { if (state.openId === closing) closeSidebar(); }, 280);
    return;
  }
  setSheet(stateName);
  keepOpenEventVisible();
}

// Drag the sheet by its handle (or anywhere while it only peeks); a flick or the
// nearest position decides where it settles. A tap on the peek opens it fully.
let drag = null;
let suppressClick = false;
const DRAG_START = 6; // px before a touch counts as a drag
const FLICK = 0.5; // px per ms

sidebar.addEventListener("pointerdown", (e) => {
  if (!isPhone() || sheet.state === "closed" || (e.pointerType === "mouse" && e.button !== 0)) return;
  const onHeader = Boolean(e.target.closest(".sidebar-header"));
  if (!onHeader && sheet.state !== "peek") return; // the full sheet scrolls its text instead
  if (e.target.closest("button, a, input, select")) return;
  const offset = sheetOffset(sheet.state);
  drag = { id: e.pointerId, startY: e.clientY, offset, y: offset, lastY: e.clientY, lastT: e.timeStamp, v: 0, moved: false };
});

window.addEventListener("pointermove", (e) => {
  if (!drag || e.pointerId !== drag.id) return;
  const dy = e.clientY - drag.startY;
  if (!drag.moved) {
    if (Math.abs(dy) < DRAG_START) return;
    drag.moved = true;
    sidebar.setPointerCapture(e.pointerId);
  }
  const dt = Math.max(1, e.timeStamp - drag.lastT);
  drag.v = (e.clientY - drag.lastY) / dt;
  drag.lastY = e.clientY;
  drag.lastT = e.timeStamp;
  drag.y = Math.max(0, drag.offset + dy);
  placeSheet(drag.y, false);
});

function endDrag(e) {
  if (!drag || e.pointerId !== drag.id) return;
  const { moved, y, v } = drag;
  drag = null;
  if (!moved) return;
  suppressClick = true;
  setTimeout(() => { suppressClick = false; }, 0);
  if (e.type === "pointercancel") {
    setSheet(sheet.state);
    return;
  }
  const positions = { full: 0, peek: sheetOffset("peek"), closed: sheetHeight() };
  let target;
  if (v > FLICK) target = y < positions.peek ? "peek" : "closed";
  else if (v < -FLICK) target = "full";
  else {
    target = Object.keys(positions).reduce((best, name) =>
      (Math.abs(positions[name] - y) < Math.abs(positions[best] - y) ? name : best), "full");
  }
  changeSheet(target);
}
// On the window: a mouse that leaves the sheet before the drag starts is not captured yet.
window.addEventListener("pointerup", endDrag);
window.addEventListener("pointercancel", endDrag);

sidebar.addEventListener("click", (e) => {
  if (suppressClick) {
    e.preventDefault();
    e.stopPropagation();
    return;
  }
  if (!isPhone() || e.target.closest("button, a, input, select")) return;
  if (sheet.state === "peek") changeSheet("full");
  else if (sheet.state === "full" && e.target.closest(".sidebar-header")) changeSheet("peek");
}, true);

function setFiltersOpen(open) {
  document.body.classList.toggle("filters-open", open);
  document.querySelector(".filters-fab")?.setAttribute("aria-expanded", String(open));
}

// A tap on the free part of the map closes the drawer.
map.on("click", () => { if (isPhone()) setFiltersOpen(false); });

// Popups pan clear of the floating buttons (read when a popup opens, from the defaults).
function updatePopupPadding() {
  L.Popup.prototype.options.autoPanPaddingTopLeft = isPhone() ? L.point(5, FAB_SPACE + 5) : null;
}
updatePopupPadding();

// Turning the phone or resizing the window: put the sheet where it belongs.
phoneQuery.addEventListener("change", () => {
  updatePopupPadding();
  setFiltersOpen(false);
  if (!isPhone()) resetSheet();
  else if (!sidebar.hidden) openSheet(true);
});
window.addEventListener("resize", debounce(() => {
  if (isPhone() && !sidebar.hidden && sheet.state !== "closed") setSheet(sheet.state, { animate: false });
}, 150));

/** The phone's Filters button says how many filters are on; the drawer's button how many events. */
function updateFilterSummary() {
  const slider = document.getElementById("year-slider")?.noUiSlider;
  let active = 0;
  if (state.category !== "all") active += 1;
  if (state.tagIds.length) active += 1;
  if (state.queryText) active += 1;
  if (slider) {
    const { min, max } = slider.options.range;
    if (state.yearFrom > min || state.yearTo < max) active += 1;
  }
  const fab = document.querySelector(".filters-fab");
  if (fab) {
    fab.querySelector("[data-filters-label]").textContent = active ? `Filters (${active} active)` : "Filters";
    fab.classList.toggle("has-active", active > 0);
  }
  const count = document.querySelector("[data-filters-done-count]");
  if (count) count.textContent = state.filtered.length === 1 ? "1 event" : `${state.filtered.length} events`;
}

// -------------------------------------------------------------- filtering

// ------------------------------------------------------------------ search

const search = {
  terms: [], // lower-case words and "quoted phrases"
  patterns: [], // one RegExp per term
  in: "all", // "all" = titles and descriptions, "title" = titles only
  match: "all", // every term must match, or "any"
  whole: false, // whole words only
  sort: "best",
};

const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function parseQuery(text) {
  const terms = [];
  const re = /"([^"]+)"|(\S+)/g;
  let m;
  while ((m = re.exec(text.toLowerCase()))) {
    const term = (m[1] || m[2]).trim();
    if (term) terms.push(term);
  }
  return terms;
}

function setQuery(text) {
  search.terms = parseQuery(text);
  search.patterns = search.terms.map((term) => {
    const body = escapeRegExp(term).replace(/\s+/g, "\\s+");
    return new RegExp(search.whole ? `(?<![\\p{L}\\p{N}])${body}(?![\\p{L}\\p{N}])` : body, "iu");
  });
  state.query = search.terms.join(" ");
  state.queryText = (text || "").trim(); // as typed, for the page address
}

/** Lower-cased texts to search, built once per event. */
function searchText(event) {
  if (event._title === undefined || event._excerpt !== event.excerpt) {
    event._excerpt = event.excerpt;
    event._title = event.title.toLowerCase();
    event._text = `${event.excerpt} ${event.display_year} ${event.date} ${event.year}`.toLowerCase();
  }
  return event;
}

/** 0 = no match; higher = better (title hits count more than description hits). */
function searchScore(event) {
  if (!search.patterns.length) return 1;
  searchText(event);
  let score = 0;
  let hits = 0;
  search.patterns.forEach((pattern, i) => {
    let s = 0;
    if (pattern.test(event._title)) s = event._title.startsWith(search.terms[i]) ? 4 : 3;
    else if (search.in === "all" && pattern.test(event._text)) s = 1;
    if (s) hits += 1;
    score += s;
  });
  if (search.match === "all" ? hits < search.patterns.length : hits === 0) return 0;
  return score;
}

// ------------------------------------------------------------------- tags
// Several tags can be selected (shown as chips); an event needs any or all of
// them. The selection lives in the page address (?tag=12&tag=34&tagmode=all),
// so a filtered map can be shared and the browser's Back button undoes a change.

const hasTags = () => state.tagIds.length > 0;

function tagMatch(event) {
  if (!state.tagIds.length) return true;
  return state.tagMode === "all"
    ? state.tagIds.every((id) => event.tags.includes(id))
    : state.tagIds.some((id) => event.tags.includes(id));
}

/** "Napoleonic Wars", "Seven Years' War / American Revolutionary War" or "3 tags". */
function tagNames() {
  const names = state.tagIds.map((id) => state.tagsById.get(id)?.name).filter(Boolean);
  if (names.length > 2) return `${names.length} tags`;
  return names.join(state.tagMode === "all" ? " & " : " / ");
}

// ----------------------------------------------------- filters in the URL
// ?tag=176&tag=179&tagmode=all&cat=naval&q=napoleon&from=1805&to=1812 – so a
// filtered map can be shared or bookmarked. A tag change is a new history entry
// (Back undoes it); typing, dragging the slider or a category only update the
// current one, so Back does not step through every keystroke.

const URL_KEYS = ["tag", "tagmode", "cat", "q", "from", "to"];
let restoringUrl = false; // while a link's filters are applied, do not rewrite it

function filtersFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const year = (key) => (params.has(key) ? parseYearText(params.get(key)) : null);
  const category = params.get("cat");
  return {
    ids: params.getAll("tag").map(Number).filter((id) => state.tagsById.has(id)),
    mode: params.get("tagmode") === "all" ? "all" : "any",
    category: category && CATEGORY_LABELS[category] ? category : "all",
    q: (params.get("q") || "").slice(0, 200),
    from: year("from"),
    to: year("to"),
  };
}

function syncUrl(push = false) {
  if (restoringUrl) return;
  const url = new URL(window.location);
  URL_KEYS.forEach((key) => url.searchParams.delete(key));
  state.tagIds.forEach((id) => url.searchParams.append("tag", id));
  if (state.tagMode === "all" && state.tagIds.length > 1) url.searchParams.set("tagmode", "all");
  if (state.category !== "all") url.searchParams.set("cat", state.category);
  if (state.queryText) url.searchParams.set("q", state.queryText);
  const slider = document.getElementById("year-slider")?.noUiSlider;
  if (slider) {
    // Only years narrowed by hand: the slider's own range follows the tags and search.
    const { min, max } = slider.options.range;
    if (state.yearFrom > min) url.searchParams.set("from", state.yearFrom);
    if (state.yearTo < max) url.searchParams.set("to", state.yearTo);
  }
  if (url.href === window.location.href) return;
  history[push ? "pushState" : "replaceState"](null, "", url);
}

/** Apply the filters of a link (on load, and when Back/Forward changes the address). */
function applyUrlFilters(filters) {
  restoringUrl = true;
  try {
    state.tagIds = filters.ids;
    state.tagMode = filters.mode;
    state.category = filters.category;
    markCategory(filters.category);
    ["search", "search-big"].forEach((id) => {
      const input = document.getElementById(id);
      if (input) input.value = filters.q;
    });
    setQuery(filters.q);
    renderTagChips();
    refilter(); // also fits the year slider to the tags and search
    const slider = document.getElementById("year-slider")?.noUiSlider;
    if (slider && (filters.from !== null || filters.to !== null)) {
      const { min, max } = slider.options.range;
      slider.set([filters.from ?? min, filters.to ?? max]); // values outside the range are clamped
    }
  } finally {
    restoringUrl = false;
  }
}

function setTags(ids, { push = true } = {}) {
  state.tagIds = [...new Set(ids)].filter((id) => state.tagsById.has(id));
  renderTagChips();
  syncUrl(push);
  refilter();
  zoomToTags();
}

// Choosing a tag flies the map to where its events are – but only for regional
// tags (the Russo-Ukrainian War, the American Civil War), not worldwide ones
// (World War II, the Cold War), where the whole map is the right view.
const REGIONAL_LAT_SPAN = 30; // degrees: about a large country or a small continent
const REGIONAL_LON_SPAN = 45;

function quantile(sorted, q) {
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))];
}

function zoomToTags() {
  if (!hasTags()) return;
  const events = state.events.filter(tagMatch);
  if (!events.length) return;
  // The middle 80% of the events, so a few far-away ones (a strike abroad, an
  // embassy treaty) don't make a regional war look worldwide.
  const lats = events.map((e) => e.lat).sort((a, b) => a - b);
  const lons = events.map((e) => e.lon).sort((a, b) => a - b);
  const south = quantile(lats, 0.1);
  const north = quantile(lats, 0.9);
  const west = quantile(lons, 0.1);
  const east = quantile(lons, 0.9);
  if (north - south > REGIONAL_LAT_SPAN || east - west > REGIONAL_LON_SPAN) return; // worldwide
  const filtersShown = !document.body.classList.contains("filters-hidden") && !isPhone();
  map.flyToBounds([[south, west], [north, east]], {
    paddingTopLeft: [filtersShown ? 340 : 40, isPhone() ? FAB_SPACE : 40],
    paddingBottomRight: [40, 60 + coveredBottom()],
    maxZoom: 7, // "vaguely": the region, not a street
    duration: 0.9,
  });
}

const addTag = (id) => setTags([...state.tagIds, id]);
const removeTag = (id) => setTags(state.tagIds.filter((t) => t !== id));
const onlyTag = (id) => setTags([id]);

function setTagMode(mode) {
  if (mode === state.tagMode) return;
  state.tagMode = mode;
  renderTagChips();
  syncUrl(true);
  refilter();
}

window.addEventListener("popstate", () => applyUrlFilters(filtersFromUrl()));

/** A tag as a button: click shows only that tag, Ctrl/Shift-click adds it to the selection. */
function tagButton(tag) {
  const button = el("button", "tag tag-btn", tag.name);
  button.type = "button";
  const selected = state.tagIds.includes(tag.id);
  button.classList.toggle("tag-selected", selected);
  button.setAttribute("aria-pressed", String(selected));
  button.title = `Show only events tagged “${tag.name}” (Ctrl- or Shift-click to add it to the selected tags)`;
  button.addEventListener("click", (e) => {
    e.stopPropagation();
    if (e.ctrlKey || e.metaKey || e.shiftKey) addTag(tag.id);
    else onlyTag(tag.id);
  });
  return button;
}

/** The selected tags as chips (in the filter panel and above the event list). */
function renderTagChips() {
  syncTagSearch();
  document.querySelectorAll("[data-tag-chips]").forEach((box) => {
    box.hidden = !hasTags();
    if (!hasTags()) {
      box.replaceChildren();
      return;
    }
    const chips = state.tagIds.map((id) => {
      const tag = state.tagsById.get(id);
      const chip = el("span", "tag-chip");
      chip.append(el("span", "tag-chip-name", tag.name), el("span", "tag-chip-years", tag.display_range));
      const remove = el("button", "tag-chip-remove", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", `Remove the tag ${tag.name}`);
      remove.addEventListener("click", () => removeTag(id));
      chip.append(remove);
      return chip;
    });
    const tools = el("div", "tag-chip-tools");
    if (state.tagIds.length > 1) {
      const mode = el("div", "tag-mode");
      mode.setAttribute("role", "group");
      mode.setAttribute("aria-label", "How several tags combine");
      [["any", "Any of them"], ["all", "All of them"]].forEach(([value, label]) => {
        const b = el("button", "tag-mode-btn", label);
        b.type = "button";
        b.setAttribute("aria-pressed", String(state.tagMode === value));
        b.classList.toggle("active", state.tagMode === value);
        b.title = value === "any" ? "Events with at least one of the tags" : "Only events that have every tag";
        b.addEventListener("click", () => setTagMode(value));
        mode.append(b);
      });
      tools.append(mode);
    }
    const clear = el("button", "tag-chip-clear", state.tagIds.length > 1 ? "Clear tags" : "Clear tag");
    clear.type = "button";
    clear.addEventListener("click", () => setTags([]));
    tools.append(clear);
    box.replaceChildren(el("div", "tag-chips", null), tools);
    box.firstChild.append(...chips);
  });
}

/** The tag menu: counts that follow the other filters; empty and selected tags hidden. */
function updateTagOptions() {
  const select = document.getElementById("tag-filter");
  if (!select) return;
  [...select.options].forEach((option, index) => {
    if (index === 0) {
      option.textContent = hasTags() ? "Add another tag…" : "All tags – choose one…";
      return;
    }
    const id = Number(option.value);
    const tag = state.tagsById.get(id);
    const count = state.tagCounts.get(id) || 0;
    const hide = count === 0 || state.tagIds.includes(id);
    option.hidden = hide;
    option.disabled = hide; // Safari ignores "hidden" on options
    option.textContent = `${tag.name} (${tag.display_range}) – ${count.toLocaleString()}`;
  });
}

/** Every filter except the tags (their counts are taken from these events). */
function matchesBase(event) {
  if (event.year < state.yearFrom || event.year > state.yearTo) return false;
  if (state.category !== "all" && event.category !== state.category) return false;
  return searchScore(event) > 0;
}

const matches = (event) => matchesBase(event) && tagMatch(event);

/** With tags selected the timeline spans their years (within the year slider). */
function timelineRange() {
  const tags = state.tagIds.map((id) => state.tagsById.get(id))
    .filter((tag) => tag && tag.start_year !== null && tag.start_year !== undefined);
  if (!tags.length) return null;
  const now = new Date().getFullYear();
  return {
    from: Math.max(Math.min(...tags.map((t) => t.start_year)), state.yearFrom),
    to: Math.min(Math.max(...tags.map((t) => t.end_year ?? now)), state.yearTo),
    label: tagNames(),
  };
}

/**
 * Show the events that match the filters. ``added``: events that just arrived in a
 * chunk while the filters stayed the same, so only their markers are added instead
 * of rebuilding all of them.
 */
function applyFilters({ added = null } = {}) {
  // One pass: the events shown, and per tag how many events match the other filters.
  state.tagCounts = new Map();
  state.filtered = [];
  state.events.forEach((event) => {
    if (!matchesBase(event)) return;
    event.tags.forEach((id) => state.tagCounts.set(id, (state.tagCounts.get(id) || 0) + 1));
    if (tagMatch(event)) state.filtered.push(event);
  });
  updateTagOptions();
  syncUrl();

  const colorRange = [state.colorFrom, state.colorTo];
  updateColorRange();
  const sameColors = !state.colorByYear || (colorRange[0] === state.colorFrom && colorRange[1] === state.colorTo);
  if (added && !state.heatmap && sameColors) {
    const markers = added.filter(matches).map((e) => {
      const marker = state.markersById.get(e.id);
      marker.setIcon(state.colorByYear ? yearIcon(e.year) : markerIcon(e.category));
      return marker;
    });
    clusters.addLayers(markers);
    finishRender();
    return;
  }

  clusters.clearLayers();
  if (heatLayer) {
    map.removeLayer(heatLayer);
    heatLayer = null;
  }
  if (state.heatmap) {
    heatLayer = L.heatLayer(state.filtered.map((e) => [e.lat, e.lon, 0.6]), { radius: 25, blur: 18, maxZoom: 10 });
    heatLayer.addTo(map);
  } else {
    // Markers off the map only store their new icon, so this is cheap.
    state.filtered.forEach((e) => {
      state.markersById.get(e.id).setIcon(state.colorByYear ? yearIcon(e.year) : markerIcon(e.category));
    });
    clusters.addLayers(state.filtered.map((e) => state.markersById.get(e.id)).filter((m) => m !== selectedMarker));
  }
  if (selectedMarker) {  // stays on the map, outside the clusters, with its ring
    if (!map.hasLayer(selectedMarker)) selectedMarker.addTo(map);
    ringOn(selectedMarker);
  }
  finishRender();
}

/** Everything around the markers: legend, timeline, count, list and search results. */
function finishRender() {
  const showLegend = state.colorByYear && !state.heatmap;
  if (showLegend && !legend.getContainer()?.parentNode) legend.addTo(map);
  if (!showLegend && legend.getContainer()?.parentNode) legend.remove();
  if (showLegend) updateLegend();

  timeline.update(state.filtered.map((e) => ({
    id: e.id, year: e.year, title: e.title, label: e.date || e.display_year, category: e.category,
  })), timelineRange());

  const total = state.events.length;
  const shown = state.filtered.length.toLocaleString();
  let count = state.filtered.length === total ? `${total.toLocaleString()} events` : `${shown} of ${total.toLocaleString()} events`;
  if (state.loading) count += " (still loading…)";
  document.getElementById("result-count").textContent = count;
  updateFilterSummary();
  renderList();
  renderSearchResults();
}

const LIST_PAGE = 60;
let listLimit = LIST_PAGE;

function renderList() {
  const grid = document.getElementById("events-grid");
  const template = document.getElementById("event-card-template");

  if (!state.filtered.length) {
    const empty = state.loading ? "Loading events…" : state.events.length ? "No events match the filters." : "No events yet.";
    grid.replaceChildren(el("p", "empty-state", empty));
    return;
  }

  const fragment = document.createDocumentFragment();
  state.filtered.slice(0, listLimit).forEach((event) => {
    const card = template.content.firstElementChild.cloneNode(true);
    const pill = card.querySelector(".year-pill");
    pill.textContent = event.display_year;
    paintYearPill(pill, event.year);
    const badge = card.querySelector(".badge");
    badge.classList.add(`badge-${event.category}`);
    badge.textContent = CATEGORY_LABELS[event.category];
    card.querySelector(".event-card-title").textContent = event.title;
    card.querySelector(".event-card-summary").textContent = event.excerpt;
    const tags = card.querySelector(".event-card-tags");
    event.tags.forEach((tagId) => {
      const tag = state.tagsById.get(tagId);
      if (tag) tags.append(tagButton(tag));
    });
    card.querySelector(".event-card-main").addEventListener("click", () => {
      showEvent(event.id);
      document.getElementById("map").scrollIntoView({ behavior: "smooth" });
    });
    const link = card.querySelector(".event-card-link");
    const wiki = safeWikipediaUrl(event.wiki_url);
    if (wiki) link.href = wiki; else link.remove();
    fragment.append(card);
  });

  if (state.filtered.length > listLimit) {
    const more = el("button", "btn btn-secondary load-more", `Show more (${state.filtered.length - listLimit} remaining)`);
    more.type = "button";
    more.addEventListener("click", () => { listLimit += LIST_PAGE * 2; renderList(); });
    fragment.append(more);
  }
  grid.replaceChildren(fragment);
}

const refilter = () => {
  listLimit = LIST_PAGE;
  rescaleYears();
  applyFilters();
};

// ---------------------------------------------------------------- controls

/** "1066", "-44", "44 BC", "AD 9", "9 CE" → a year (negative = BC); null if not a year. */
function parseYearText(text) {
  const m = /^\s*(?:(AD|CE)\s*)?(-)?(\d{1,5})\s*(BC|BCE|B\.C\.|AD|CE)?\s*$/i.exec(text || "");
  if (!m || (m[2] && (m[1] || m[4]))) return null;
  let year = Number(m[3]);
  if (m[2] || /^b/i.test(m[4] || "")) year = -year;
  return year || null; // there is no year 0
}

/** Slider range; over long spans modern centuries get more room (most events are recent). */
function sliderRange(min, max) {
  if (min === max) { min -= 1; max += 1; } // noUiSlider needs a non-empty range
  const range = { min, max };
  if (max - min > 1000) {
    const stops = [[0, "35%"], [1500, "65%"], [1900, "85%"]];
    stops.forEach(([year, pos]) => { if (year > min && year < max) range[pos] = year; });
  }
  return range;
}

/** Events that match everything except the year filter. */
function matchesIgnoringYears(event) {
  if (state.category !== "all" && event.category !== state.category) return false;
  if (!tagMatch(event)) return false;
  return searchScore(event) > 0;
}

let yearScopeKey = "";
let yearsNarrowed = false;
let yearsTouched = false; // the years were changed by hand (not by a link or a tag)

/**
 * A chunk arrived while the slider is fitted to a tag or search: widen it to the
 * matching events loaded now, keeping ends someone moved inward by hand.
 */
function widenYearScope() {
  const slider = document.getElementById("year-slider").noUiSlider;
  if (!slider || !yearsNarrowed) return;
  const years = state.events.filter(matchesIgnoringYears).map((e) => e.year);
  if (!years.length) return;
  let min = years[0];
  let max = years[0];
  years.forEach((y) => { if (y < min) min = y; if (y > max) max = y; });
  const what = [hasTags() ? tagNames() : null,
    search.terms.length ? `“${search.terms.join(" ")}”` : null].filter(Boolean).join(" + ");
  document.getElementById("year-scope").textContent =
    `Slider fitted to ${what}: ${years.length.toLocaleString()} event${years.length === 1 ? "" : "s"}`;
  const range = slider.options.range;
  if (min >= range.min && max <= range.max) return;
  const [from, to] = slider.get().map(Number);
  slider.updateOptions({ range: sliderRange(Math.min(min, range.min), Math.max(max, range.max)) }, false);
  slider.set([from <= range.min ? min : from, to >= range.max ? max : to]);
}

/**
 * With a tag or a search, the whole slider spans just the years of the matching
 * events (so years can be picked precisely); without them it spans all events.
 * Only acts when the tags or the search changed – not the years or the category.
 */
function rescaleYears() {
  const slider = document.getElementById("year-slider").noUiSlider;
  if (!slider) return;
  // The category is not part of it: switching it keeps the years someone set by hand.
  const key = JSON.stringify([state.tagIds, state.tagMode, state.query, search.in, search.match, search.whole]);
  if (key === yearScopeKey) return;
  yearScopeKey = key;
  const scope = document.getElementById("year-scope");
  const narrowed = hasTags() || search.terms.length > 0;
  const wasNarrowed = yearsNarrowed;
  yearsNarrowed = narrowed;
  // Only the category changed, with no tag or search: keep the years someone set by hand.
  if (!narrowed && !wasNarrowed && slider.options.range.min === state.allYears.min) return;
  const years = narrowed ? state.events.filter(matchesIgnoringYears).map((e) => e.year) : [];
  let min = state.allYears.min;
  let max = state.allYears.max;
  if (years.length) {
    min = Math.min(...years);
    max = Math.max(...years);
    const what = [hasTags() ? tagNames() : null,
      search.terms.length ? `“${search.terms.join(" ")}”` : null].filter(Boolean).join(" + ");
    scope.textContent = `Slider fitted to ${what}: ${years.length.toLocaleString()} event${years.length === 1 ? "" : "s"}`;
  } else {
    scope.textContent = "";
  }
  slider.updateOptions({ range: sliderRange(min, max) }, false);
  slider.set([min, max]);
}

function setupYearSlider(years) {
  const slider = document.getElementById("year-slider");
  const fromInput = document.getElementById("year-from");
  const toInput = document.getElementById("year-to");
  const min = Math.min(...years);
  const max = Math.max(...years);
  state.allYears = { min, max };
  const range = sliderRange(min, max);

  noUiSlider.create(slider, {
    start: [range.min, range.max],
    connect: true,
    step: 1,
    range,
    format: { to: (v) => Math.round(v), from: (v) => Number(v) },
    handleAttributes: [{ "aria-label": "From year" }, { "aria-label": "To year" }],
  });

  const update = debounce(refilter, 120);
  slider.noUiSlider.on("start", () => { yearsTouched = true; });
  slider.noUiSlider.on("update", ([from, to]) => {
    if (document.activeElement !== fromInput) fromInput.value = formatYear(from);
    if (document.activeElement !== toInput) toInput.value = formatYear(to);
    state.yearFrom = from;
    state.yearTo = to;
    update();
  });

  // Typing a year: Enter or leaving the box applies it, a wrong entry goes back.
  const apply = (input, index) => {
    yearsTouched = true;
    const year = parseYearText(input.value);
    const values = slider.noUiSlider.get().map(Number);
    if (year === null) {
      input.value = formatYear(values[index]);
      input.classList.add("year-input-invalid");
      setTimeout(() => input.classList.remove("year-input-invalid"), 900);
      return;
    }
    const { min: low, max: high } = slider.noUiSlider.options.range;
    const clamped = Math.min(Math.max(year, low), high);
    const next = [...values];
    next[index] = clamped;
    if (next[0] > next[1]) next[1 - index] = clamped; // typed past the other end: move both
    slider.noUiSlider.set(next);
    input.value = formatYear(clamped);
  };
  [[fromInput, 0], [toInput, 1]].forEach(([input, index]) => {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        apply(input, index);
      } else if (e.key === "Escape") {
        input.value = formatYear(Number(slider.noUiSlider.get()[index]));
        input.blur();
      }
    });
    input.addEventListener("change", () => apply(input, index));
    input.addEventListener("focus", () => input.select());
  });
}

function markCategory(category) {
  document.querySelectorAll(".category-btn").forEach((b) => {
    const active = b.dataset.category === category;
    b.classList.toggle("active", active);
    b.setAttribute("aria-pressed", String(active));
  });
}

function setupCategoryButtons() {
  document.querySelectorAll(".category-btn").forEach((button) => {
    button.addEventListener("click", () => {
      markCategory(button.dataset.category);
      state.category = button.dataset.category;
      refilter();
    });
  });
}

function setupTagFilter(tags) {
  // Every tag: while chunks are loading it is not known yet which ones are used.
  // Tags without matching events are hidden by updateTagOptions anyway.
  const select = document.getElementById("tag-filter");
  tags.forEach((tag) => {
    const option = el("option", null, `${tag.name} (${tag.display_range})`);
    option.value = tag.id;
    select.append(option);
  });
  select.addEventListener("change", () => {
    if (select.value) addTag(Number(select.value));
    select.value = "";
  });
  setupTagSearch(tags);
}

// ------------------------------------------------------------- tag search

const TAG_SUGGESTIONS = 12;
let syncTagSearch = () => {};

const foldText = (text) => text.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** The large "Filter by tag" box above the event list (kept in sync with the tag menu). */
function setupTagSearch(tags) {
  const input = document.getElementById("tag-search");
  const list = document.getElementById("tag-search-list");
  const clear = document.getElementById("tag-search-clear");
  const select = document.getElementById("tag-filter");
  const entries = tags.map((tag) => ({ tag, key: foldText(tag.name) }));
  const countOf = (tag) => state.tagCounts.get(tag.id) || 0;
  let options = [];
  let active = -1;

  function choose(tag) {
    input.value = "";
    close();
    if (tag) addTag(tag.id);
    else setTags([]);
  }

  function close() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    active = -1;
  }

  function show() {
    const query = foldText(input.value.trim());
    const words = query.split(/\s+/).filter(Boolean);
    options = entries
      .filter((e) => words.every((w) => e.key.includes(w)) && countOf(e.tag) > 0 && !state.tagIds.includes(e.tag.id))
      .sort((a, b) => (b.key.startsWith(query) - a.key.startsWith(query)) || countOf(b.tag) - countOf(a.tag)
        || a.tag.name.localeCompare(b.tag.name))
      .slice(0, TAG_SUGGESTIONS);
    active = -1;
    const items = options.map((entry, i) => {
      const li = el("li", "tag-search-option");
      li.id = `tag-option-${i}`;
      li.setAttribute("role", "option");
      li.append(el("span", "tag-search-name", entry.tag.name),
        el("span", "tag-search-meta", `${entry.tag.display_range} · ${countOf(entry.tag).toLocaleString()} events`));
      li.addEventListener("mousedown", (e) => { e.preventDefault(); choose(entry.tag); });
      return li;
    });
    if (!items.length) {
      items.push(el("li", "tag-search-empty",
        "No tag with matching events – try a shorter word, or widen the years, category or search."));
    }
    list.replaceChildren(...items);
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function move(step) {
    if (list.hidden) show();
    if (!options.length) return;
    active = (active + step + options.length) % options.length;
    list.querySelectorAll(".tag-search-option").forEach((li, i) => li.classList.toggle("active", i === active));
    input.setAttribute("aria-activedescendant", `tag-option-${active}`);
    list.children[active].scrollIntoView({ block: "nearest" });
  }

  syncTagSearch = () => {
    clear.hidden = !hasTags();
    input.placeholder = hasTags()
      ? "Add another tag – e.g. Seven Years' War…"
      : "Type a war, era or period – e.g. Napoleonic, Cold War, Crusades…";
  };

  input.addEventListener("input", show);
  input.addEventListener("focus", () => { input.select(); show(); });
  input.addEventListener("blur", () => setTimeout(close, 120));
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter") {
      e.preventDefault();
      if (options.length) choose(options[Math.max(active, 0)].tag);
    } else if (e.key === "Escape") {
      close();
      input.blur();
    }
  });
  clear.addEventListener("click", () => choose(null));
}

const RESULTS_PAGE = 100;
const searchPanel = document.getElementById("search-panel");
const searchResults = document.getElementById("search-results");
let resultsLimit = RESULTS_PAGE;
let activeResult = -1;

/** The text with every matched term wrapped in <mark> (built from text nodes, never HTML). */
function highlighted(text) {
  const box = document.createDocumentFragment();
  if (!search.patterns.length || !text) {
    box.append(text || "");
    return box;
  }
  // Short words ("of", "a") still have to match, but highlighting them everywhere is noise.
  const shown = search.patterns.filter((_, i) => search.terms[i].length >= 3);
  if (!shown.length) {
    box.append(text);
    return box;
  }
  const source = shown.map((p) => `(?:${p.source})`).join("|");
  const re = new RegExp(source, "giu");
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (!m[0]) continue;
    box.append(text.slice(last, m.index), el("mark", null, m[0]));
    last = m.index + m[0].length;
  }
  box.append(text.slice(last));
  return box;
}

function sortedResults() {
  const results = state.filtered.slice();
  const byYear = (a, b) => a.year - b.year || a.title.localeCompare(b.title);
  if (search.sort === "oldest") results.sort(byYear);
  else if (search.sort === "newest") results.sort((a, b) => -byYear(a, b));
  else if (search.sort === "title") results.sort((a, b) => a.title.localeCompare(b.title));
  else {
    const scores = new Map(results.map((e) => [e.id, searchScore(e)]));
    results.sort((a, b) => scores.get(b.id) - scores.get(a.id) || byYear(a, b));
  }
  return results;
}

function renderSearchResults() {
  if (searchPanel.hidden) return;
  const status = document.getElementById("search-status");
  const results = sortedResults();
  const total = state.events.length;
  const loadingNote = state.loading ? " (more are still loading)" : state.textsLoading && search.in === "all"
    ? " (descriptions are still loading)" : "";
  const filtersOn = state.category !== "all" || hasTags() || state.filtered.length < total && !search.terms.length;
  status.textContent = !search.terms.length
    ? `Type to search ${total.toLocaleString()} events${filtersOn ? " (filters apply)" : ""}.`
    : results.length
      ? `${results.length.toLocaleString()} event${results.length === 1 ? "" : "s"} match${loadingNote}`
      : "No events match. Try “Any word”, fewer words, or clear the year, category and tag filters.";

  if (!search.terms.length) {
    searchResults.replaceChildren();
    return;
  }
  const items = results.slice(0, resultsLimit).map((event, index) => {
    const li = el("li");
    const button = el("button", "search-result");
    button.type = "button";
    button.dataset.index = index;
    const meta = el("span", "search-result-meta");
    const pill = el("span", "year-pill", event.date || event.display_year);
    paintYearPill(pill, event.year);
    meta.append(pill, el("span", `badge badge-${event.category}`, CATEGORY_LABELS[event.category]));
    const title = el("span", "search-result-title");
    title.append(highlighted(event.title));
    const excerpt = el("span", "search-result-excerpt");
    excerpt.append(highlighted(event.excerpt));
    button.append(meta, title, excerpt);
    button.addEventListener("click", () => openResult(event.id));
    li.append(button);
    const adder = collectionAdder.control(event.id, { compact: true });
    if (adder) {
      li.className = "search-item";
      li.append(adder);
    }
    return li;
  });
  if (results.length > resultsLimit) {
    const more = el("button", "btn btn-secondary btn-small search-more",
      `Show ${Math.min(RESULTS_PAGE, results.length - resultsLimit)} more (${(results.length - resultsLimit).toLocaleString()} left)`);
    more.type = "button";
    more.addEventListener("click", () => { resultsLimit += RESULTS_PAGE; renderSearchResults(); });
    const li = el("li");
    li.append(more);
    items.push(li);
  }
  searchResults.replaceChildren(...items);
  activeResult = -1;
}

function openResult(id) {
  closeSearchPanel();
  showEvent(id, { zoom: CLICK_ZOOM });
}

function openSearchPanel() {
  const big = document.getElementById("search-big");
  big.value = document.getElementById("search").value;
  searchPanel.hidden = false;
  document.body.classList.add("search-open");
  resultsLimit = RESULTS_PAGE;
  renderSearchResults();
  big.focus();
  big.select();
}

function closeSearchPanel() {
  searchPanel.hidden = true;
  document.body.classList.remove("search-open");
  document.getElementById("search-expand").focus({ preventScroll: true });
}

function moveActive(step) {
  const buttons = [...searchResults.querySelectorAll(".search-result")];
  if (!buttons.length) return;
  activeResult = (activeResult + step + buttons.length) % buttons.length;
  buttons.forEach((b, i) => b.classList.toggle("active", i === activeResult));
  buttons[activeResult].scrollIntoView({ block: "nearest" });
}

function setupSearch() {
  const small = document.getElementById("search");
  const big = document.getElementById("search-big");
  const run = debounce(() => {
    resultsLimit = RESULTS_PAGE;
    refilter();
  }, 200);
  const onInput = (source, other) => () => {
    other.value = source.value;
    setQuery(source.value);
    run();
  };
  small.addEventListener("input", onInput(small, big));
  big.addEventListener("input", onInput(big, small));

  const options = { "search-in": "in", "search-match": "match", "search-sort": "sort" };
  Object.entries(options).forEach(([id, key]) => {
    document.getElementById(id).addEventListener("change", (e) => {
      search[key] = e.target.value;
      setQuery(big.value);
      if (key === "sort") renderSearchResults(); else refilter();
    });
  });
  document.getElementById("search-whole").addEventListener("change", (e) => {
    search.whole = e.target.checked;
    setQuery(big.value);
    refilter();
  });

  document.getElementById("search-expand").addEventListener("click", openSearchPanel);
  document.getElementById("search-close").addEventListener("click", closeSearchPanel);
  searchPanel.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); closeSearchPanel(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); moveActive(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); moveActive(-1); }
    else if (e.key === "Enter" && e.target === big) {
      e.preventDefault();
      const target = searchResults.querySelectorAll(".search-result")[Math.max(activeResult, 0)];
      if (target) target.click();
    }
  });
  // "/" or Ctrl+K opens the large search from anywhere except a text field.
  document.addEventListener("keydown", (e) => {
    const typing = /^(input|textarea|select)$/i.test(e.target.tagName) || e.target.isContentEditable;
    if ((e.key === "/" && !typing) || (e.key.toLowerCase() === "k" && (e.ctrlKey || e.metaKey))) {
      e.preventDefault();
      openSearchPanel();
    }
  });
}

function setupHeatmapToggle() {
  const button = document.getElementById("heatmap-toggle");
  button.addEventListener("click", () => {
    state.heatmap = !state.heatmap;
    button.classList.toggle("active", state.heatmap);
    button.setAttribute("aria-pressed", String(state.heatmap));
    button.querySelector("span").textContent = state.heatmap ? "Heatmap on" : "Heatmap";
    if (!state.heatmap) map.getContainer().classList.remove("heat-clickable");
    applyFilters();
  });
}

const COLOR_PREF = "haam.colorByYear";

function setupColorToggle() {
  const button = document.getElementById("color-toggle");
  const render = () => {
    button.classList.toggle("active", state.colorByYear);
    button.setAttribute("aria-pressed", String(state.colorByYear));
    button.querySelector("span").textContent = state.colorByYear ? "Colour by year on" : "Colour by year";
  };
  try {
    state.colorByYear = localStorage.getItem(COLOR_PREF) === "1";
  } catch { /* storage blocked: start with the setting off */ }
  render();
  button.addEventListener("click", () => {
    state.colorByYear = !state.colorByYear;
    try {
      localStorage.setItem(COLOR_PREF, state.colorByYear ? "1" : "0");
    } catch { /* not remembered, still works */ }
    render();
    applyFilters();
    if (state.openId !== null && !sidebar.hidden) showEvent(state.openId, { fly: false });
  });
}

function setupFilterPanelToggle() {
  document.querySelectorAll("[data-toggle-filters]").forEach((button) => {
    button.addEventListener("click", () => {
      if (isPhone()) {
        setFiltersOpen(!document.body.classList.contains("filters-open"));
        return;
      }
      document.body.classList.toggle("filters-hidden");
      setTimeout(() => map.invalidateSize(), 310);
    });
  });
}

// -------------------------------------------------------------------- start

const progressBox = document.getElementById("map-progress");

function showProgress(loaded, total, text) {
  if (!progressBox) return;
  progressBox.hidden = false;
  progressBox.querySelector(".map-progress-text").textContent =
    text || `Loading ${loaded.toLocaleString()} of ${total.toLocaleString()} events…`;
  progressBox.querySelector(".map-progress-bar span").style.width = `${total ? Math.round((100 * loaded) / total) : 0}%`;
}

function hideProgress() {
  if (progressBox) progressBox.hidden = true;
}

function loadFailed() {
  hideProgress();
  document.getElementById("events-grid").replaceChildren(
    el("p", "empty-state", "Could not load events. Please reload the page."));
}

/** Add one chunk of events (already in event-object form) to the loaded ones. */
function addEvents(events) {
  events.sort(compareEvents);
  events.forEach((event) => {
    state.eventsById.set(event.id, event);
    state.markersById.set(event.id, createMarker(event));
  });
  state.events = mergeSorted(state.events, events);
}

// ?event=id opens that event as soon as its chunk is there (it is loaded first).
const requestedId = Number(new URLSearchParams(window.location.search).get("event")) || null;
let requestedShown = false;

function openRequested() {
  if (requestedShown || !requestedId || !state.eventsById.has(requestedId)) return;
  requestedShown = true;
  showEvent(requestedId);
}

/** Tags, the year slider and the filters of the link, once the first events are there. */
function start(tags, years) {
  tags.forEach((tag) => state.tagsById.set(tag.id, tag));
  setupTagFilter(tags);
  if (years.length && years[0] !== null) {
    setupYearSlider(years);
  } else {
    document.getElementById("year-slider").replaceChildren(el("p", "form-hint", "No events yet."));
  }
  // Filters from the page address (?tag=…&q=…&from=…), e.g. a shared link.
  applyUrlFilters(filtersFromUrl());
  openRequested();
}

/** The main map: the chunks listed in the manifest the page carries (haam/feed.py). */
async function loadChunked(manifest) {
  state.total = manifest.total;
  state.loading = true;
  state.textsLoading = true;
  const urlYears = filtersFromUrl();
  const order = chunkOrder(manifest, requestedId);
  showProgress(0, manifest.total);

  // The first chunk alone (so it has the whole connection), then the others together.
  let tags;
  let firstChunk;
  try {
    [tags, firstChunk] = await Promise.all([getJsonRetry(manifest.tags), getJsonRetry(manifest.core[order[0]])]);
  } catch (error) {
    console.error(error);
    loadFailed();
    return;
  }
  addEvents(decodeCore(firstChunk));
  start(tags, manifest.years);
  showProgress(state.events.length, manifest.total);
  performance.mark("haam:first-markers");

  const results = await Promise.allSettled(order.slice(1).map((n) => getJsonRetry(manifest.core[n]).then((chunk) => {
    const events = decodeCore(chunk);
    addEvents(events);
    showProgress(state.events.length, manifest.total);
    if (yearsNarrowed) widenYearScope();
    applyFilters({ added: events });
    openRequested();
  })));
  state.loading = false;
  const failed = results.filter((r) => r.status === "rejected");
  failed.forEach((r) => console.error(r.reason));

  // Years from the link that the first chunk's events could not hold yet.
  const slider = document.getElementById("year-slider").noUiSlider;
  if (slider && !yearsTouched && (urlYears.from !== null || urlYears.to !== null)) {
    const { min, max } = slider.options.range;
    slider.set([urlYears.from ?? min, urlYears.to ?? max]);
  }
  finishRender(); // the count without "still loading"
  performance.mark("haam:all-markers");

  // The short descriptions: popups, the list and searching in descriptions.
  showProgress(state.events.length, manifest.total, "Loading descriptions…");
  const texts = await Promise.allSettled(manifest.text.map((url) => getJsonRetry(url).then((chunk) => {
    chunk.id.forEach((id, i) => {
      const event = state.eventsById.get(id);
      if (event) event.excerpt = chunk.excerpt[i];
    });
  })));
  state.textsLoading = false;
  texts.filter((r) => r.status === "rejected").forEach((r) => console.error(r.reason));
  if (failed.length) {
    showProgress(state.events.length, manifest.total,
      `Loaded ${state.events.length.toLocaleString()} of ${manifest.total.toLocaleString()} events – reload for the rest`);
  } else {
    hideProgress();
  }
  // A search in descriptions now finds more; the list and popups get their text.
  if (search.terms.length && search.in === "all") {
    if (yearsNarrowed) widenYearScope();
    applyFilters();
  } else {
    renderList();
    renderSearchResults();
  }
  if (state.openId !== null && !sidebar.hidden) showEvent(state.openId, { fly: false });
}

/** A collection's map: one small list that already carries the full text. */
async function loadSingle() {
  let events;
  let tags;
  try {
    [events, tags] = await Promise.all([getJson(EVENTS_URL), getJson("/api/tags")]);
  } catch (error) {
    console.error(error);
    loadFailed();
    return;
  }
  events.forEach((event) => { event.display_year = event.display_year || formatYear(event.year); });
  addEvents(events);
  state.total = events.length;
  const years = events.map((e) => e.year);
  start(tags, years.length ? [Math.min(...years), Math.max(...years)] : []);
}

async function init() {
  collectionAdder.load();
  setupCategoryButtons();
  setupSearch();
  setupHeatmapToggle();
  setupColorToggle();
  setupFilterPanelToggle();

  const manifest = MAP_ELEMENT.dataset.manifest ? JSON.parse(MAP_ELEMENT.dataset.manifest) : null;
  if (manifest) await loadChunked(manifest); else await loadSingle();
}

init();
