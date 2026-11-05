// Map on a collection page: one marker per entry, linked to the list beside it.
/* global L */

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
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18,
  }).addTo(map);

  const markers = new Map();
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
    marker.on("click", () => highlight(entry.id, false));
    markers.set(entry.id, marker);
  });

  const points = entries.map((e) => [e.lat, e.lon]);
  if (points.length === 1) map.setView(points[0], 6);
  else map.fitBounds(points, { padding: [40, 40], maxZoom: 8 });

  function highlight(id, scroll) {
    document.querySelectorAll(".entry-card.active").forEach((c) => c.classList.remove("active"));
    const card = document.getElementById(`entry-${id}`);
    if (!card) return;
    card.classList.add("active");
    if (scroll) card.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  document.querySelectorAll("[data-entry-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = Number(button.dataset.entryId);
      const marker = markers.get(id);
      if (!marker) return;
      highlight(id, false);
      map.flyTo(marker.getLatLng(), Math.max(map.getZoom(), 6), { duration: 0.7 });
      marker.openPopup();
      mapElement.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  });
}
