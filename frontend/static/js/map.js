document.addEventListener("DOMContentLoaded", () => {
  const mapDiv = document.getElementById("map");
  const dataDiv = document.getElementById("map-data");
  if (!mapDiv || !dataDiv) return;

  const entries = JSON.parse(dataDiv.dataset.entries);

  const map = L.map('map').setView([50, 10], 4); // Center Europe

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);

  entries.forEach((entry) => {
    if (!entry.coordinates) return;

    const parts = entry.coordinates.split(',').map(s => parseFloat(s.trim()));
    if (parts.length < 2 || parts.some(isNaN)) return;
    const [lat, lon] = parts;

    let paragraph = entry.first_paragraph || "";
    if (paragraph.length > 220) paragraph = paragraph.slice(0, 217) + '...';

    let popupHtml = `<strong>${entry.title || "Untitled"}</strong><br>`;
    if (entry.year) popupHtml += `<em>${entry.year}</em><br>`;
    popupHtml += `${paragraph}<br>`;
    if (entry.link) popupHtml += `<a href="${entry.link}" target="_blank" rel="noopener">Read more</a>`;

    L.marker([lat, lon]).addTo(map).bindPopup(popupHtml);
  });
});
