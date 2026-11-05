// <div data-location-picker data-lat="#lat" data-lon="#lon">: click the map to fill
// the latitude/longitude inputs; typing coordinates moves the marker.
/* global L */

document.querySelectorAll("[data-location-picker]").forEach((element) => {
  const latInput = document.querySelector(element.dataset.lat);
  const lonInput = document.querySelector(element.dataset.lon);
  if (!latInput || !lonInput) return;

  const map = L.map(element, { worldCopyJump: true, minZoom: 1 }).setView([35, 15], 2);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18,
  }).addTo(map);

  let marker = null;
  const round = (value) => Math.round(value * 1e5) / 1e5; // ~1 m

  function place(lat, lon, { pan = false } = {}) {
    if (marker) marker.setLatLng([lat, lon]);
    else {
      marker = L.marker([lat, lon], { draggable: true }).addTo(map);
      marker.on("dragend", () => {
        const pos = marker.getLatLng().wrap();
        latInput.value = round(pos.lat);
        lonInput.value = round(pos.lng);
      });
    }
    if (pan) map.setView([lat, lon], Math.max(map.getZoom(), 5));
  }

  map.on("click", (event) => {
    const pos = event.latlng.wrap(); // keep longitude within -180..180
    latInput.value = round(pos.lat);
    lonInput.value = round(pos.lng);
    place(pos.lat, pos.lng);
  });

  function fromInputs(pan) {
    const lat = parseFloat(latInput.value);
    const lon = parseFloat(lonInput.value);
    if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
      place(lat, lon, { pan });
    }
  }
  latInput.addEventListener("change", () => fromInputs(true));
  lonInput.addEventListener("change", () => fromInputs(true));
  fromInputs(true); // editing an existing entry, or re-showing a form with errors
});
