import "../css/base.css";
import "../css/map.css";
import { fetchEvents } from "./api.js";
import { initNav, setActiveNav } from "./nav.js";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import noUiSlider from "nouislider";
import "nouislider/dist/nouislider.css";

let map;
let markers = [];
let eventsData = [];
let eventsById = new Map();
let selectedCategory = "all";
let yearRange = { from: 0, to: 3000 };

const customIcon = L.divIcon({
  className: "custom-marker-icon",
  html:
    '<div style="background:#4299e1;width:16px;height:16px;border-radius:50%;border:3px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.3);"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

function normalizeEvent(entry) {
  if (!entry.location) return null;
  return {
    id: entry.id,
    lat: entry.location.lat,
    lon: entry.location.lon,
    title: entry.title || "Untitled",
    year: entry.year,
    date: entry.date,
    description: entry.first_paragraph || "",
    link: entry.link || "",
    category: entry.category || "other",
  };
}

function computeCenter(events) {
  if (!events.length) return [20, 0];
  const lat = events.reduce((sum, e) => sum + e.lat, 0) / events.length;
  const lon = events.reduce((sum, e) => sum + e.lon, 0) / events.length;
  return [lat, lon];
}

function filterEvents() {
  return eventsData.filter((event) => {
    const year = parseInt(event.year, 10);
    const yearOk = !isNaN(year) && year >= yearRange.from && year <= yearRange.to;
    const categoryOk = selectedCategory === "all" || event.category === selectedCategory;
    return yearOk && categoryOk;
  });
}

function addMarkers(filteredEvents) {
  markers.forEach((m) => map.removeLayer(m));
  markers = [];

  filteredEvents.forEach((event) => {
    const truncated =
      event.description.length > 150
        ? `${event.description.substring(0, 150)}...`
        : event.description;

    const popupContent = `
      <div class="popup-content">
        <strong>${event.title}</strong>
        ${event.year ? `<em>${event.year}</em><br><br>` : ""}
        ${truncated}
      </div>
      <button class="popup-btn" data-event-id="${event.id}">View Full Details →</button>
    `;

    const marker = L.marker([event.lat, event.lon], { icon: customIcon })
      .bindPopup(popupContent, { maxWidth: 300 })
      .addTo(map);

    marker.on("popupopen", () => {
      const btn = document.querySelector(`.popup-btn[data-event-id="${event.id}"]`);
      btn?.addEventListener("click", () => showEvent(event.id));
    });

    markers.push(marker);
  });
}

function renderEventCards(filteredEvents) {
  const grid = document.getElementById("events-grid");
  if (!grid) return;

  grid.innerHTML = filteredEvents
    .map(
      (event) => `
      <div class="event-card" data-event-id="${event.id}">
        <div class="event-card-year">${event.year}</div>
        <div class="event-card-category">${(event.category || "other").replace(/^./, (c) => c.toUpperCase())}</div>
        <div class="event-card-title">${event.title}</div>
        <div class="event-card-description">${event.description}</div>
        ${event.link ? `<a href="${event.link}" target="_blank" rel="noopener" class="event-card-link" onclick="event.stopPropagation()">Read more →</a>` : ""}
      </div>
    `
    )
    .join("");

  grid.querySelectorAll(".event-card").forEach((card) => {
    card.addEventListener("click", () => {
      const id = parseInt(card.dataset.eventId, 10);
      showEvent(id);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

function applyFilters() {
  const filtered = filterEvents();
  addMarkers(filtered);
  renderEventCards(filtered);
}

function showEvent(eventId) {
  const event = eventsById.get(eventId);
  if (!event) return;

  const sidebar = document.getElementById("sidebar");
  const content = document.getElementById("sidebar-content");

  content.innerHTML = `
    <span class="event-detail-year">${event.year}</span>
    <h3 class="event-detail-title">${event.title}</h3>
    <div class="event-detail-coordinates">📍 ${event.lat.toFixed(4)}, ${event.lon.toFixed(4)}</div>
    <div class="event-detail-description">${event.description}</div>
    ${event.link ? `<a href="${event.link}" target="_blank" rel="noopener" class="event-detail-link">Read Full Article →</a>` : ""}
  `;

  sidebar.classList.add("active");
  document.getElementById("map").classList.add("with-sidebar");
  map.setView([event.lat, event.lon], 5, { animate: true });
}

window.closeSidebar = function closeSidebar() {
  document.getElementById("sidebar").classList.remove("active");
  document.getElementById("map").classList.remove("with-sidebar");
};

window.scrollToEvents = function scrollToEvents() {
  document.getElementById("events-section")?.scrollIntoView({ behavior: "smooth" });
};

function setupYearSlider(events) {
  const years = events.map((e) => parseInt(e.year, 10)).filter((y) => !isNaN(y));
  if (!years.length) return;

  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  yearRange = { from: minYear, to: maxYear };

  const slider = document.getElementById("year-slider");
  const fromDisplay = document.getElementById("year-from-display");
  const toDisplay = document.getElementById("year-to-display");

  noUiSlider.create(slider, {
    start: [minYear, maxYear],
    connect: true,
    step: 1,
    range: { min: minYear, max: maxYear },
  });

  fromDisplay.textContent = minYear;
  toDisplay.textContent = maxYear;

  slider.noUiSlider.on("update", (values) => {
    yearRange.from = Math.round(values[0]);
    yearRange.to = Math.round(values[1]);
    fromDisplay.textContent = yearRange.from;
    toDisplay.textContent = yearRange.to;
    applyFilters();
  });
}

function setupCategoryFilter() {
  document.querySelectorAll(".category-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".category-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      selectedCategory = btn.dataset.category;
      applyFilters();
    });
  });
}

async function initMapPage() {
  initNav();
  setActiveNav("home");

  map = L.map("map", {
    center: [20, 0],
    zoom: 2,
    minZoom: 2,
    maxZoom: 18,
    worldCopyJump: true,
  });

  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap & CARTO",
    maxZoom: 18,
  }).addTo(map);

  try {
    const entries = await fetchEvents();
    eventsData = entries.map(normalizeEvent).filter(Boolean);
    eventsById = new Map(eventsData.map((e) => [e.id, e]));

    if (eventsData.length) {
      map.setView(computeCenter(eventsData), 3);
    }

    setupYearSlider(eventsData);
    setupCategoryFilter();
    applyFilters();
  } catch (err) {
    console.error(err);
    document.getElementById("events-grid").innerHTML =
      `<p class="error-message">Failed to load events: ${err.message}</p>`;
  }
}

document.addEventListener("DOMContentLoaded", initMapPage);
