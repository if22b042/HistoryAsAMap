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
};

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

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
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
    return L.divIcon({
      html: `<span>${count}</span>`, // a number we computed – safe
      className: `cluster cluster-${size}`,
      iconSize: L.point(40, 40),
    });
  },
}).addTo(map);

let heatLayer = null;

function markerIcon(category) {
  return L.divIcon({
    className: `marker marker-${category}`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -9],
  });
}

function popupContent(event) {
  const box = el("div", "popup");
  box.append(el("strong", "popup-title", event.title));
  box.append(el("span", "popup-year", event.date || event.display_year));
  const summary = event.summary.length > 160 ? `${event.summary.slice(0, 157)}…` : event.summary;
  box.append(el("p", "popup-summary", summary));
  const button = el("button", "popup-btn", "View details →");
  button.type = "button";
  button.addEventListener("click", () => showEvent(event.id));
  box.append(button);
  return box;
}

function createMarker(event) {
  return L.marker([event.lat, event.lon], { icon: markerIcon(event.category), title: event.title })
    .bindPopup(() => popupContent(event), { maxWidth: 300 });
}

// ------------------------------------------------------------------ sidebar

const sidebar = document.getElementById("sidebar");
const sidebarContent = document.getElementById("sidebar-content");

function showEvent(id, { fly = true } = {}) {
  const event = state.eventsById.get(id);
  if (!event) return;

  const parts = [];
  parts.push(el("span", "year-pill", event.date || event.display_year));
  parts.push(el("h3", "detail-title", event.title));

  const meta = el("p", "detail-meta");
  const badge = el("span", `badge badge-${event.category}`, CATEGORY_LABELS[event.category]);
  meta.append(badge, ` ${event.lat.toFixed(4)}, ${event.lon.toFixed(4)}`);
  if (event.country) meta.append(` · ${event.country}`);
  parts.push(meta);

  parts.push(el("p", "detail-summary", event.summary));

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
    const haystack = `${event.title} ${event.summary} ${event.display_year} ${event.date}`.toLowerCase();
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
  if (state.heatmap) {
    heatLayer = L.heatLayer(state.filtered.map((e) => [e.lat, e.lon, 0.6]), { radius: 25, blur: 18, maxZoom: 10 });
    heatLayer.addTo(map);
  } else {
    clusters.addLayers(state.filtered.map((e) => state.markersById.get(e.id)));
  }

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
    card.querySelector(".year-pill").textContent = event.display_year;
    const badge = card.querySelector(".badge");
    badge.classList.add(`badge-${event.category}`);
    badge.textContent = CATEGORY_LABELS[event.category];
    card.querySelector(".event-card-title").textContent = event.title;
    card.querySelector(".event-card-summary").textContent = event.summary;
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
