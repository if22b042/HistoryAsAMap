// Base maps shared by every map on the site, and a small switcher control for
// the bottom-right corner. The choice is kept in localStorage so each map opens
// with the style picked last.
//
// All sources are free to use without an API key, as long as their attribution
// is shown (Leaflet's attribution control does that for the active layer).
// (CARTO's basemaps would fit too, but they now answer browsers with an
// "API key required" tile.)
/* global L */

const OSM = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const MAX_ZOOM = 18;

const isDark = () => document.documentElement.dataset.theme === "dark";
const ESRI_CANVAS = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas";
const grayCanvas = (layer) => () => `${ESRI_CANVAS}/World_${isDark() ? "Dark" : "Light"}_Gray_${layer}/MapServer/tile/{z}/{y}/{x}`;
const ESRI_CANVAS_ATTRIBUTION = "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors, and the GIS user community";

// url (and labels, an overlay with place names) may be a function of the theme:
// those layers follow the theme toggle.
export const BASEMAPS = {
  street: {
    label: "Street",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    options: { attribution: OSM },
  },
  terrain: {
    label: "Terrain",
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    // OpenTopoMap has tiles up to zoom 17; Leaflet enlarges them beyond that.
    options: {
      subdomains: "abc",
      maxNativeZoom: 17,
      attribution: `Map data: ${OSM}, SRTM | Style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)`,
    },
  },
  satellite: {
    label: "Satellite",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    options: { attribution: "Imagery &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community" },
  },
  // Esri's light or dark gray canvas, with its place names on top.
  minimal: {
    label: "Minimal",
    url: grayCanvas("Base"),
    labels: grayCanvas("Reference"),
    options: { maxNativeZoom: 16, attribution: ESRI_CANVAS_ATTRIBUTION },
  },
  // The same canvas without place names: the Game's map (which must not name
  // the places the player is looking for), offered on the other maps too.
  plain: {
    label: "Plain",
    url: grayCanvas("Base"),
    options: { maxNativeZoom: 16, attribution: ESRI_CANVAS_ATTRIBUTION },
  },
};

const DEFAULT_CHOICES = ["street", "terrain", "satellite", "minimal", "plain"];

function readChoice(key) {
  try { return localStorage.getItem(key); } catch (e) { return null; }
}

function saveChoice(key, id) {
  try { localStorage.setItem(key, id); } catch (e) { /* storage blocked */ }
}

function tileLayer(url, options) {
  const layer = L.tileLayer(typeof url === "function" ? url() : url, { maxZoom: MAX_ZOOM, ...options });
  if (typeof url === "function") layer.followTheme = () => layer.setUrl(url());
  return layer;
}

// The base map behind everything else, plus its label overlay if it has one.
function createLayer(id) {
  const { url, labels, options } = BASEMAPS[id];
  const group = L.layerGroup([tileLayer(url, { ...options, zIndex: 0 })]);
  if (labels) group.addLayer(tileLayer(labels, { ...options, attribution: "", zIndex: 1 }));
  return group;
}

// Swatch colours that hint at each style in the menu.
const SWATCH = { street: "#f2efe9", terrain: "#c9d8a6", satellite: "#3d5a3a", minimal: "#e5e7eb", plain: "#d4d4d4" };

const ICON = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" '
  + 'stroke-width="2" stroke-linejoin="round"><path d="M12 3 2 8l10 5 10-5-10-5Z"/><path d="m2 13 10 5 10-5"/></svg>';

/**
 * Add the base map to `map` and a switcher to its bottom-right corner.
 * choices: which BASEMAPS to offer (the first is the default);
 * storageKey: where the choice is remembered (maps that offer other choices,
 * like the Game, use their own key).
 */
export function addBasemapSwitcher(map, { choices = DEFAULT_CHOICES, storageKey = "basemap", position = "bottomright" } = {}) {
  const layers = {};
  let current = null;
  const container = map.getContainer();

  function select(id) {
    if (!choices.includes(id)) id = choices[0];
    if (id === current) return;
    if (current) {
      map.removeLayer(layers[current]);
      container.classList.remove(`basemap-${current}`);
    }
    layers[id] ||= createLayer(id);
    layers[id].addTo(map);
    container.classList.add(`basemap-${id}`);
    current = id;
    control.getContainer()?.querySelectorAll("[data-basemap]").forEach((button) => {
      button.setAttribute("aria-checked", String(button.dataset.basemap === id));
    });
  }

  const control = L.control({ position });
  control.onAdd = () => {
    const box = L.DomUtil.create("div", "basemap-switcher leaflet-bar");
    const toggle = L.DomUtil.create("button", "basemap-toggle", box);
    toggle.type = "button";
    toggle.title = "Map style";
    toggle.setAttribute("aria-label", "Map style");
    toggle.setAttribute("aria-expanded", "false");
    toggle.innerHTML = ICON; // a constant – safe

    const menu = L.DomUtil.create("div", "basemap-menu", box);
    menu.setAttribute("role", "radiogroup");
    menu.setAttribute("aria-label", "Map style");
    menu.hidden = true;
    for (const id of choices) {
      const option = L.DomUtil.create("button", "basemap-option", menu);
      option.type = "button";
      option.dataset.basemap = id;
      option.setAttribute("role", "radio");
      option.setAttribute("aria-checked", String(id === current));
      const swatch = L.DomUtil.create("span", "basemap-swatch", option);
      swatch.style.background = SWATCH[id];
      option.append(BASEMAPS[id].label);
      option.addEventListener("click", () => {
        select(id);
        saveChoice(storageKey, id);
        open(false);
        toggle.focus();
      });
    }

    function open(show) {
      menu.hidden = !show;
      toggle.setAttribute("aria-expanded", String(show));
      if (!show) return;
      // Opens upwards, moved down as far as needed to stay inside the map
      // (the controls sit high above the open timeline on a phone).
      menu.style.bottom = "";
      const overflow = container.getBoundingClientRect().top + 4 - menu.getBoundingClientRect().top;
      if (overflow > 0) menu.style.bottom = `${-overflow}px`;
      menu.querySelector('[aria-checked="true"]')?.focus();
    }
    toggle.addEventListener("click", () => open(menu.hidden));
    box.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !menu.hidden) {
        open(false);
        toggle.focus();
      }
    });
    document.addEventListener("click", (event) => {
      if (!menu.hidden && !box.contains(event.target)) open(false);
    });
    map.on("movestart", () => open(false));

    L.DomEvent.disableClickPropagation(box);
    L.DomEvent.disableScrollPropagation(box);
    return box;
  };
  control.addTo(map);
  select(readChoice(storageKey));

  // Theme-dependent styles switch to their light or dark tiles.
  new MutationObserver(() => {
    Object.values(layers).forEach((group) => group.eachLayer((layer) => layer.followTheme?.()));
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  return control;
}
