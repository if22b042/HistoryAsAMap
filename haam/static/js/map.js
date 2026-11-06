// Map page: loads approved events from the API, shows them as clustered markers
// (or a heatmap), filters by year/category/tag/text and lists them below the map.
/* global L, noUiSlider */

const CATEGORY_LABELS = {
  military: "Military",
  diplomatic: "Diplomatic",
  naval: "Naval",
  scientific: "Scientific",
  other: "Other",
};

const state = {
  events: [],
  eventsById: new Map(),
  markersById: new Map(),
  tagsById: new Map(),
  filtered: [],
  yearFrom: -Infinity,
  yearTo: Infinity,
  category: "all",
  tagId: null,
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

function formatYear(year) {
  if (year === null || year === undefined) return "";
  if (year < 0) return `${-year} BC`;
  if (year < 1000) return `AD ${year}`;
  return String(year);
}

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

async function getJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
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
    return L.divIcon({
      html: `<span>${count}</span>`, // a number we computed – safe
      className: `cluster cluster-${size}`,
      iconSize: L.point(40, 40),
    });
  },
}).addTo(map);

let heatLayer = null;

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
  box.append(el("p", "popup-summary", event.excerpt));
  const button = el("button", "popup-btn", "View details →");
  button.type = "button";
  button.addEventListener("click", () => showEvent(event.id));
  box.append(button);
  return box;
}

function createMarker(event) {
  return L.marker([event.lat, event.lon], { icon: markerIcon(event.category), title: event.title, year: event.year })
    .bindPopup(() => popupContent(event), { maxWidth: 300 });
}

// ------------------------------------------------------------------ sidebar

const sidebar = document.getElementById("sidebar");
const sidebarContent = document.getElementById("sidebar-content");

const detailsCache = new Map();

async function loadDetails(id) {
  if (!detailsCache.has(id)) {
    detailsCache.set(id, getJson(`/api/events/${id}`).catch((error) => {
      console.error(error);
      detailsCache.delete(id);
      return null;
    }));
  }
  return detailsCache.get(id);
}

function showEvent(id, { fly = true } = {}) {
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
      if (tag) tags.append(el("span", "tag", tag.name));
    });
    parts.push(tags);
  }

  const actions = el("div", "detail-actions");
  const wiki = safeWikipediaUrl(event.wiki_url);
  if (wiki) {
    const link = el("a", "btn btn-primary", "Read on Wikipedia");
    link.href = wiki;
    link.target = "_blank";
    link.rel = "noopener";
    actions.append(link);
  }
  const maps = el("a", "btn btn-secondary", "Google Maps");
  maps.href = `https://www.google.com/maps?q=${event.lat},${event.lon}`;
  maps.target = "_blank";
  maps.rel = "noopener";
  actions.append(maps);
  parts.push(actions);

  state.openId = id;
  sidebarContent.replaceChildren(...parts);
  sidebar.hidden = false;
  document.body.classList.add("sidebar-open");

  const url = new URL(window.location);
  url.searchParams.set("event", id);
  history.replaceState(null, "", url);

  if (fly) {
    map.closePopup();
    map.flyTo([event.lat, event.lon], Math.max(map.getZoom(), 6), { duration: 0.8 });
  }
}

function closeSidebar() {
  sidebar.hidden = true;
  document.body.classList.remove("sidebar-open");
  const url = new URL(window.location);
  url.searchParams.delete("event");
  history.replaceState(null, "", url);
}

document.getElementById("sidebar-close").addEventListener("click", closeSidebar);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !sidebar.hidden) closeSidebar(); });

// -------------------------------------------------------------- filtering

function matches(event) {
  if (event.year < state.yearFrom || event.year > state.yearTo) return false;
  if (state.category !== "all" && event.category !== state.category) return false;
  if (state.tagId !== null && !event.tags.includes(state.tagId)) return false;
  if (state.query) {
    const haystack = `${event.title} ${event.excerpt} ${event.display_year} ${event.date}`.toLowerCase();
    if (!haystack.includes(state.query)) return false;
  }
  return true;
}

function applyFilters() {
  state.filtered = state.events.filter(matches);

  clusters.clearLayers();
  if (heatLayer) {
    map.removeLayer(heatLayer);
    heatLayer = null;
  }
  updateColorRange();
  if (state.heatmap) {
    heatLayer = L.heatLayer(state.filtered.map((e) => [e.lat, e.lon, 0.6]), { radius: 25, blur: 18, maxZoom: 10 });
    heatLayer.addTo(map);
  } else {
    // Markers off the map only store their new icon, so this is cheap.
    state.filtered.forEach((e) => {
      state.markersById.get(e.id).setIcon(state.colorByYear ? yearIcon(e.year) : markerIcon(e.category));
    });
    clusters.addLayers(state.filtered.map((e) => state.markersById.get(e.id)));
  }

  const showLegend = state.colorByYear && !state.heatmap;
  if (showLegend && !legend.getContainer()?.parentNode) legend.addTo(map);
  if (!showLegend && legend.getContainer()?.parentNode) legend.remove();
  if (showLegend) updateLegend();

  const total = state.events.length;
  document.getElementById("result-count").textContent =
    state.filtered.length === total ? `${total} events` : `${state.filtered.length} of ${total} events`;
  renderList();
}

const LIST_PAGE = 60;
let listLimit = LIST_PAGE;

function renderList() {
  const grid = document.getElementById("events-grid");
  const template = document.getElementById("event-card-template");

  if (!state.filtered.length) {
    grid.replaceChildren(el("p", "empty-state", state.events.length ? "No events match the filters." : "No events yet."));
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
      if (tag) tags.append(el("span", "tag", tag.name));
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

const refilter = () => { listLimit = LIST_PAGE; applyFilters(); };

// ---------------------------------------------------------------- controls

function setupYearSlider(years) {
  const slider = document.getElementById("year-slider");
  const fromLabel = document.getElementById("year-from");
  const toLabel = document.getElementById("year-to");
  let min = Math.min(...years);
  let max = Math.max(...years);
  if (min === max) { min -= 1; max += 1; } // noUiSlider needs a non-empty range

  // Most events are recent, so give modern centuries more room on the slider.
  const range = { min, max };
  if (max - min > 1000) {
    const stops = [[0, "35%"], [1500, "65%"], [1900, "85%"]];
    stops.forEach(([year, pos]) => { if (year > min && year < max) range[pos] = year; });
  }

  noUiSlider.create(slider, {
    start: [min, max],
    connect: true,
    step: 1,
    range,
    format: { to: (v) => Math.round(v), from: (v) => Number(v) },
    handleAttributes: [{ "aria-label": "From year" }, { "aria-label": "To year" }],
  });

  const update = debounce(refilter, 120);
  slider.noUiSlider.on("update", ([from, to]) => {
    fromLabel.textContent = formatYear(from);
    toLabel.textContent = formatYear(to);
    state.yearFrom = from;
    state.yearTo = to;
    update();
  });
}

function setupCategoryButtons() {
  const buttons = document.querySelectorAll(".category-btn");
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      buttons.forEach((b) => {
        const active = b === button;
        b.classList.toggle("active", active);
        b.setAttribute("aria-pressed", String(active));
      });
      state.category = button.dataset.category;
      refilter();
    });
  });
}

function setupTagFilter(tags) {
  const select = document.getElementById("tag-filter");
  const used = new Set(state.events.flatMap((e) => e.tags));
  tags.filter((t) => used.has(t.id)).forEach((tag) => {
    const option = el("option", null, `${tag.name} (${tag.display_range})`);
    option.value = tag.id;
    select.append(option);
  });
  select.addEventListener("change", () => {
    state.tagId = select.value ? Number(select.value) : null;
    refilter();
  });
}

function setupSearch() {
  const input = document.getElementById("search");
  input.addEventListener("input", debounce(() => {
    state.query = input.value.trim().toLowerCase();
    refilter();
  }, 200));
}

function setupHeatmapToggle() {
  const button = document.getElementById("heatmap-toggle");
  button.addEventListener("click", () => {
    state.heatmap = !state.heatmap;
    button.classList.toggle("active", state.heatmap);
    button.setAttribute("aria-pressed", String(state.heatmap));
    button.querySelector("span").textContent = state.heatmap ? "Heatmap on" : "Heatmap";
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
      document.body.classList.toggle("filters-hidden");
      setTimeout(() => map.invalidateSize(), 310);
    });
  });
}

// -------------------------------------------------------------------- start

async function init() {
  setupCategoryButtons();
  setupSearch();
  setupHeatmapToggle();
  setupColorToggle();
  setupFilterPanelToggle();

  let events;
  let tags;
  try {
    [events, tags] = await Promise.all([getJson("/api/events"), getJson("/api/tags")]);
  } catch (error) {
    console.error(error);
    document.getElementById("events-grid").replaceChildren(
      el("p", "empty-state", "Could not load events. Please reload the page."));
    return;
  }

  state.events = events;
  events.forEach((event) => {
    state.eventsById.set(event.id, event);
    state.markersById.set(event.id, createMarker(event));
  });
  tags.forEach((tag) => state.tagsById.set(tag.id, tag));

  setupTagFilter(tags);
  if (events.length) {
    setupYearSlider(events.map((e) => e.year));
  } else {
    document.getElementById("year-slider").replaceChildren(el("p", "form-hint", "No events yet."));
  }
  applyFilters();

  const requested = Number(new URLSearchParams(window.location.search).get("event"));
  if (requested && state.eventsById.has(requested)) showEvent(requested);
}

init();
