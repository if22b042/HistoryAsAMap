// Map on a collection page: one marker per entry, linked to the list beside it.
/* global L */
import { createTimeline } from "./timeline.js";

// Map zoom when an event is picked on the timeline (9 = about a city).
const CLICK_ZOOM = 9;

const dataTag = document.getElementById("collection-data");
const mapElement = document.getElementById("collection-map");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

if (dataTag && mapElement) {
  const entries = JSON.parse(dataTag.textContent);
  const map = L.map(mapElement, { worldCopyJump: true, minZoom: 2 });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18,
  }).addTo(map);

  const markers = new Map();
  const timeline = createTimeline({ map, limit: 500, onSelect: (id) => focusEntry(id, { zoom: CLICK_ZOOM, scrollToMap: false }) });
  entries.forEach((entry, index) => {
    const icon = L.divIcon({
      className: `marker marker-${entry.category}${entry.is_event ? "" : " marker-custom"}`,
      html: `<span>${index + 1}</span>`, // a number we computed – safe
      iconSize: [24, 24],
      iconAnchor: [12, 12],
      popupAnchor: [0, -12],
    });
    const popup = () => {
      const box = el("div", "popup");
      box.append(el("strong", "popup-title", entry.title));
      box.append(el("span", "popup-year", entry.date || entry.display_year));
      if (entry.note) box.append(el("p", "popup-summary", entry.note));
      const jump = el("button", "popup-btn", "Show in list ↓");
      jump.type = "button";
      jump.addEventListener("click", () => highlight(entry.id, true));
      box.append(jump);
      return box;
    };
    const marker = L.marker([entry.lat, entry.lon], { icon, title: entry.title }).bindPopup(popup).addTo(map);
    marker.on("click", () => {
      highlight(entry.id, false);
      timeline.setActive(entry.id);
    });
    markers.set(entry.id, marker);
  });

  const points = entries.map((e) => [e.lat, e.lon]);
  if (points.length === 1) map.setView(points[0], 6);
  else map.fitBounds(points, { padding: [40, 40], maxZoom: 8 });

  // The same black-and-white ring as on the main map marks the selected entry.
  const selectionRing = L.marker([0, 0], {
    icon: L.divIcon({ className: "selected-ring", iconSize: [44, 44], iconAnchor: [22, 22] }),
    interactive: false,
    keyboard: false,
    zIndexOffset: 10000,
  });

  function highlight(id, scroll) {
    document.querySelectorAll(".entry-card.active").forEach((c) => c.classList.remove("active"));
    const marker = markers.get(id);
    if (marker) {
      selectionRing.setLatLng(marker.getLatLng());
      if (!map.hasLayer(selectionRing)) selectionRing.addTo(map);
    }
    const card = document.getElementById(`entry-${id}`);
    if (!card) return;
    card.classList.add("active");
    if (scroll) card.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function focusEntry(id, { zoom = 6, scrollToMap = true } = {}) {
    const marker = markers.get(id);
    if (!marker) return;
    highlight(id, false);
    timeline.setActive(id);
    map.flyTo(marker.getLatLng(), Math.max(map.getZoom(), zoom), { duration: 0.7 });
    // Open the popup when the flight ends – or after a moment, in case the browser
    // paused the animation (a tab in the background).
    let opened = false;
    const openPopup = () => {
      if (!opened) {
        opened = true;
        marker.openPopup();
      }
    };
    map.once("moveend", openPopup);
    setTimeout(openPopup, 1200);
    if (scrollToMap) mapElement.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  document.querySelectorAll("[data-entry-id]").forEach((button) => {
    button.addEventListener("click", () => focusEntry(Number(button.dataset.entryId)));
  });

  timeline.update(entries.map((e) => ({
    id: e.id, year: e.year, title: e.title, label: e.date || e.display_year, category: e.category,
  })));
}
