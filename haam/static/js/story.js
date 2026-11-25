// Story mode: a collection or a tag played step by step on a map.
// The page (story.html) holds the payload, the map box and the header chip; this module builds
// the toolbar, the caption card with its controls, the dialogs, and drives the camera.
/* global L */
import { addBasemapSwitcher } from "./basemaps.js";

const STEP_ZOOM = 6;
const SPEEDS = { slow: 12000, normal: 8000, fast: 5000 };
const SPEED_LABELS = { slow: "Slow", normal: "Normal", fast: "Fast" };

const dataTag = document.getElementById("story-data");
const root = document.getElementById("story");
const mapBox = document.getElementById("story-map");
const data = dataTag && root && mapBox ? JSON.parse(dataTag.textContent) : null;

if (data && data.steps.length) start(data);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function icon(name) {
  const i = el("i", `fa-solid fa-${name}`);
  i.setAttribute("aria-hidden", "true");
  return i;
}

function button(label, iconName, className = "icon-btn") {
  const b = el("button", className);
  b.type = "button";
  b.setAttribute("aria-label", label);
  b.title = label;
  if (iconName) b.append(icon(iconName));
  return b;
}

function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch { /* storage blocked: the story still works */ }
  return null;
}

function distanceKm(aLat, aLon, bLat, bLon) {
  const rad = Math.PI / 180;
  const dLat = (bLat - aLat) * rad;
  const dLon = (bLon - aLon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(aLat * rad) * Math.cos(bLat * rad) * Math.sin(dLon / 2) ** 2;
  return 12742 * Math.asin(Math.min(1, Math.sqrt(h)));
}

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function start(story) {
  const steps = story.steps;
  const count = steps.length;
  const embed = document.body.classList.contains("page-embed");
  const hasMap = typeof L !== "undefined";
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  const pathKey = `haam.storyPath.${story.kind}`;
  const stepKey = `haam.story:${location.pathname}`;

  // ---- state
  let cur = -1; // -1: the intro is showing
  let playing = false;
  let dwellTimer = 0;
  let own = false; // true while our own camera move runs
  let moveToken = 0;
  let userZoomed = false;
  let compact = false;
  let showPath = story.path_default;
  const savedPath = store(pathKey);
  if (savedPath === "1" || savedPath === "0") showPath = savedPath === "1";
  let speed = store("haam.storySpeed");
  if (!SPEEDS[speed]) speed = "normal";

  // Longitudes unwrapped once so that a step never jumps across the date line.
  const coords = [];
  steps.forEach((step, i) => {
    let lon = step.lon;
    if (i) while (Math.abs(lon - coords[i - 1][1]) > 180) lon += lon < coords[i - 1][1] ? 360 : -360;
    coords.push([step.lat, lon]);
  });

  // ---- map
  let map = null;
  const markers = [];
  let pathLine = null;
  if (hasMap) {
    map = L.map(mapBox, { keyboard: false, worldCopyJump: true, minZoom: 2, zoomControl: false });
    map.setView([20, 0], 2); // Leaflet needs a view before markers and lines are added
    L.control.zoom({ position: "bottomright" }).addTo(map);
    addBasemapSwitcher(map);
    steps.forEach((step, i) => {
      const category = /^[a-z-]+$/.test(step.category) ? step.category : "other";
      const numbered = story.kind === "collection";
      const size = numbered ? 24 : 14;
      const html = numbered ? el("span", "", String(i + 1)) : "";
      const marker = L.marker(coords[i], {
        title: step.title,
        icon: L.divIcon({
          className: `marker marker-${category}${step.custom ? " marker-custom" : ""}`,
          html,
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
        }),
      }).addTo(map);
      marker.on("click", () => go(i));
      markers.push(marker);
    });
    map.on("dragstart", pause);
    map.on("zoomstart", () => {
      if (own) return;
      userZoomed = true;
      pause();
    });
  } else {
    mapBox.append(el("p", "form-hint", "The map could not be loaded."));
  }

  // ---- toolbar
  const toolbar = el("div", "story-toolbar pill");
  toolbar.setAttribute("role", "toolbar");
  toolbar.setAttribute("aria-label", "Story tools");
  const stepsBtn = button("Steps", "list-ol");
  const pathBtn = button("Show the path", "route");
  const speedBox = el("div", "seg story-speed");
  speedBox.setAttribute("role", "group");
  speedBox.setAttribute("aria-label", "Autoplay speed");
  const speedBtns = {};
  for (const id of Object.keys(SPEEDS)) {
    const b = el("button", "", SPEED_LABELS[id]);
    b.type = "button";
    b.addEventListener("click", () => setSpeed(id));
    speedBtns[id] = b;
    speedBox.append(b);
  }
  const shareBtn = button("Share", "share-nodes");
  shareBtn.setAttribute("aria-haspopup", "true");
  shareBtn.setAttribute("aria-expanded", "false");
  const fullBtn = button("Full screen", "expand");
  const helpBtn = button("Keyboard shortcuts", null);
  helpBtn.append(el("span", "story-help-mark", "?"));
  fullBtn.classList.add("story-full-btn");
  helpBtn.classList.add("story-help-btn");
  toolbar.append(stepsBtn, pathBtn, speedBox, shareBtn, fullBtn, helpBtn);
  if (count < 2) { pathBtn.hidden = true; speedBox.hidden = true; }
  if (embed) shareBtn.hidden = true;
  if (!document.fullscreenEnabled) fullBtn.hidden = true;

  // ---- caption panel
  const panel = el("section", "story-panel sheet");
  panel.setAttribute("aria-label", "Story");
  const handle = el("button", "story-handle");
  handle.type = "button";
  handle.append(el("span", "sheet-handle"));
  const body = el("div", "story-panel-body");
  const intro = el("div", "story-intro");
  intro.id = "story-intro";
  const caption = el("div", "story-caption");
  caption.id = "story-caption";
  caption.setAttribute("aria-live", "polite");
  caption.hidden = true;
  body.append(intro, caption);

  const controls = el("div", "story-controls");
  const row = el("div", "story-buttons");
  const prevBtn = button("Previous step", "backward-step");
  const playBtn = button("Play the story", "play");
  const nextBtn = button("Next step", "forward-step");
  const counter = el("span", "story-counter");
  counter.id = "story-counter";
  row.append(prevBtn, playBtn, nextBtn, counter);
  const range = el("input", "story-range");
  range.type = "range";
  range.id = "story-range";
  range.min = "1";
  range.max = String(count);
  range.step = "1";
  range.value = "1";
  range.setAttribute("aria-label", "Step");
  controls.append(row, range);
  controls.hidden = true;
  if (count < 2) { prevBtn.hidden = nextBtn.hidden = playBtn.hidden = range.hidden = true; }
  panel.append(handle, body, controls);
  setHandle();

  // ---- dialogs and popover
  const stepsDialog = buildStepsDialog();
  const helpDialog = buildHelpDialog();
  const share = buildShare();
  root.append(toolbar, panel, stepsDialog.dialog, helpDialog, share.box);

  buildIntro();

  // ---- wiring
  stepsBtn.addEventListener("click", () => { pause(); stepsDialog.open(); });
  helpBtn.addEventListener("click", () => { pause(); helpDialog.showModal(); });
  pathBtn.addEventListener("click", () => {
    showPath = !showPath;
    store(pathKey, showPath ? "1" : "0");
    renderPath();
    renderToolbar();
  });
  shareBtn.addEventListener("click", () => (share.box.hidden ? openShare() : closeShare()));
  fullBtn.addEventListener("click", toggleFullscreen);
  document.addEventListener("fullscreenchange", renderFullscreen);
  prevBtn.addEventListener("click", () => go(cur - 1));
  nextBtn.addEventListener("click", () => go(cur + 1));
  playBtn.addEventListener("click", togglePlay);
  range.addEventListener("input", () => go(Number(range.value) - 1));
  handle.addEventListener("click", () => {
    compact = !compact;
    setHandle();
    settleMap();
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) pause(); });
  document.addEventListener("click", (e) => {
    if (!share.box.hidden && !share.box.contains(e.target) && !shareBtn.contains(e.target)) closeShare();
  });
  document.addEventListener("keydown", onKey);
  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => map?.invalidateSize(), 150);
  });
  renderToolbar();
  renderPlay();
  renderFullscreen();

  // ---- start-up
  const wanted = Number(new URLSearchParams(location.search).get("step"));
  if (Number.isInteger(wanted) && wanted >= 1) go(Math.min(wanted, count) - 1, { instant: true }); // past the end: the last step
  else showIntro();

  // =============================================================== functions

  function showIntro() {
    cur = -1;
    intro.hidden = false;
    caption.hidden = true;
    controls.hidden = true;
    panel.classList.add("is-intro");
    markers.forEach((m, i) => selectMarker(i, false));
    renderPath();
    if (map) {
      map.invalidateSize();
      ownMove(() => {
        if (count === 1) map.setView(coords[0], 6, { animate: false });
        else map.fitBounds(coords, { padding: [40, 40], maxZoom: 8, animate: false });
      });
    }
  }

  function buildIntro() {
    intro.append(el("h2", "story-intro-title", story.title));
    if (story.intro) intro.append(el("p", "story-intro-text", story.intro));
    const meta = `${count} ${count === 1 ? "step" : "steps"}${story.years ? ` · ${story.years}` : ""}`;
    intro.append(el("p", "form-hint story-intro-meta", meta));
    const actions = el("div", "story-intro-actions");
    const startBtn = el("button", "btn btn-primary", "Start");
    startBtn.type = "button";
    startBtn.addEventListener("click", () => go(0));
    actions.append(startBtn);
    const saved = Number(store(stepKey));
    if (Number.isInteger(saved) && saved > 1 && saved <= count) {
      const more = el("button", "btn btn-secondary", `Continue at step ${saved}`);
      more.type = "button";
      more.addEventListener("click", () => go(saved - 1));
      actions.append(more);
    }
    if (story.page_url) {
      const page = el("a", "btn btn-secondary", "About this tag");
      page.href = story.page_url;
      if (embed) { page.target = "_blank"; page.rel = "noopener"; }
      actions.append(page);
    }
    intro.append(actions);
  }

  function go(index, { instant = false } = {}) {
    const i = Math.max(0, Math.min(count - 1, index));
    const wasIntro = cur === -1;
    const previous = cur;
    cur = i;
    clearTimeout(dwellTimer);
    if (wasIntro) {
      intro.hidden = true;
      caption.hidden = false;
      controls.hidden = false;
      panel.classList.remove("is-intro");
      map?.invalidateSize();
    }
    renderCaption(steps[i], i, previous !== i || wasIntro);
    counter.textContent = `${i + 1} / ${count}`;
    range.value = String(i + 1);
    range.setAttribute("aria-valuetext", `Step ${i + 1} of ${count}: ${steps[i].title}`);
    prevBtn.disabled = i === 0;
    nextBtn.disabled = i === count - 1;
    markers.forEach((_, n) => selectMarker(n, n === i));
    renderPath();
    stepsDialog.mark(i);
    syncUrl(i);
    store(stepKey, String(i + 1));
    moveCamera(coords[i], instant, () => { if (playing) armDwell(); });
  }

  function selectMarker(i, on) {
    const marker = markers[i];
    marker.setZIndexOffset(on ? 10000 : 0);
    marker.getElement()?.classList.toggle("marker-selected", on);
  }

  function syncUrl(i) {
    const url = new URL(location.href);
    url.searchParams.set("step", String(i + 1));
    try { history.replaceState(null, "", url.pathname + url.search + url.hash); } catch { /* sandboxed frame */ }
    const brand = document.getElementById("story-brand");
    if (brand) brand.href = story.story_url + location.search;
  }

  function renderCaption(step, i, fade) {
    const box = el("div", "story-caption-body");
    box.append(el("span", "sr-only", `Step ${i + 1} of ${count}:`));
    const meta = el("div", "story-meta");
    meta.append(el("span", "year-pill", step.date));
    const category = /^[a-z-]+$/.test(step.category) ? step.category : "other";
    meta.append(el("span", `badge badge-${category}`, category.charAt(0).toUpperCase() + category.slice(1)));
    if (step.custom) meta.append(el("span", "story-custom", "Custom entry"));
    box.append(meta, el("h2", "story-step-title", step.title));
    if (step.note) box.append(el("blockquote", "entry-note story-note", step.note));
    if (step.text) box.append(el("p", "story-text", step.text));
    const where = [];
    if (step.part != null && story.parts[step.part]) where.push(`Part of: ${story.parts[step.part]}`);
    if (step.country) where.push(step.country);
    if (where.length) box.append(el("p", "story-where", where.join(" · ")));
    if (step.link) {
      const link = el("a", "story-more", `${step.link_label || "Read more"} `);
      const out = el("i", "fas fa-external-link-alt");
      out.setAttribute("aria-hidden", "true");
      link.append(out);
      link.href = step.link;
      link.rel = step.custom ? "noopener noreferrer nofollow ugc" : "noopener";
      if (embed) link.target = "_blank";
      box.append(link);
    }
    if (fade && !reduce.matches) box.classList.add("story-fade");
    caption.replaceChildren(box);
    panel.scrollTop = 0;
  }

  function renderPath() {
    if (!map) return;
    const points = [];
    if (cur >= 0 && showPath) {
      for (let n = 0; n <= cur; n++) {
        const last = points[points.length - 1];
        if (!last || last[0] !== coords[n][0] || last[1] !== coords[n][1]) points.push(coords[n]);
      }
    }
    if (points.length < 2) {
      if (pathLine) { pathLine.remove(); pathLine = null; }
      return;
    }
    if (!pathLine) {
      pathLine = L.polyline(points, {
        color: cssVar("--text-strong", "#1d1d1f"), weight: 3, opacity: 0.8, dashArray: "8 6",
        interactive: false, className: "story-path",
      }).addTo(map);
    } else pathLine.setLatLngs(points);
  }

  function renderToolbar() {
    pathBtn.setAttribute("aria-pressed", String(showPath));
    for (const [id, b] of Object.entries(speedBtns)) {
      b.classList.toggle("active", id === speed);
      b.setAttribute("aria-pressed", String(id === speed));
    }
  }

  function renderPlay() {
    const label = playing ? "Pause the story" : "Play the story";
    playBtn.setAttribute("aria-label", label);
    playBtn.title = label;
    playBtn.setAttribute("aria-pressed", String(playing));
    playBtn.replaceChildren(icon(playing ? "pause" : "play"));
  }

  function setSpeed(id) {
    speed = id;
    store("haam.storySpeed", id);
    renderToolbar();
    if (playing) armDwell();
  }

  function setHandle() {
    panel.classList.toggle("is-compact", compact);
    handle.setAttribute("aria-expanded", String(!compact));
    handle.setAttribute("aria-label", compact ? "Show the whole caption" : "Show less");
  }

  function settleMap() {
    if (map) requestAnimationFrame(() => map.invalidateSize());
  }

  // ---- camera
  function ownMove(fn) {
    own = true;
    try { fn(); } finally { own = false; }
  }

  function moveCamera(target, instant, arrived) {
    if (!map) { arrived(); return; }
    const token = ++moveToken;
    const zoom = userZoomed ? map.getZoom() : STEP_ZOOM;
    userZoomed = false;
    const center = map.getCenter();
    const km = distanceKm(center.lat, center.lng, target[0], target[1]);
    if (km < 1 && map.getZoom() === zoom) { own = false; arrived(); return; }
    if (instant || reduce.matches) {
      ownMove(() => map.setView(target, zoom, { animate: false }));
      arrived();
      return;
    }
    const duration = Math.min(2, Math.max(0.6, 0.4 + km / 4000));
    own = true;
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      clearTimeout(fallback);
      map.off("moveend", finish);
      if (token !== moveToken) return; // a newer move took over
      own = false;
      arrived();
    };
    const fallback = setTimeout(finish, duration * 1000 + 500);
    map.on("moveend", finish);
    map.flyTo(target, zoom, { duration });
  }

  // ---- autoplay
  function armDwell() {
    clearTimeout(dwellTimer);
    if (own) return; // the camera is still travelling: its arrival arms the timer
    dwellTimer = setTimeout(() => {
      if (!playing) return;
      if (cur >= count - 1) pause();
      else go(cur + 1);
    }, SPEEDS[speed]);
  }

  function play() {
    if (count < 2) return;
    if (cur === -1) { go(0); }
    else if (cur >= count - 1) go(0);
    playing = true;
    renderPlay();
    armDwell();
  }

  function pause() {
    clearTimeout(dwellTimer);
    if (!playing) return;
    playing = false;
    renderPlay();
  }

  function togglePlay() { playing ? pause() : play(); }

  // ---- full screen
  function toggleFullscreen() {
    if (!document.fullscreenEnabled) return;
    const job = document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
    job?.catch?.(() => {});
  }

  function renderFullscreen() {
    const on = Boolean(document.fullscreenElement);
    const label = on ? "Exit full screen" : "Full screen";
    fullBtn.setAttribute("aria-label", label);
    fullBtn.title = label;
    fullBtn.replaceChildren(icon(on ? "compress" : "expand"));
    settleMap();
  }

  // ---- keyboard
  function onKey(e) {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    const openDialog = document.querySelector("dialog[open]");
    if (e.key === "Escape") {
      if (!share.box.hidden) { closeShare(); shareBtn.focus(); }
      return; // an open dialog closes itself on Esc
    }
    const t = e.target;
    if (t instanceof Element && t.closest("input, select, textarea")) return;
    if (openDialog) return;
    switch (e.key) {
      case "ArrowLeft": if (cur >= 0) go(cur - 1); else return; break;
      case "ArrowRight": if (cur >= 0) go(cur + 1); else go(0); break;
      case "Home": if (cur >= 0) go(0); else return; break;
      case "End": if (cur >= 0) go(count - 1); else return; break;
      case " ":
        // on a button or link, Space already does its own thing
        if (t instanceof Element && t.closest("button, a[href]")) return;
        if (cur === -1) go(0); else togglePlay();
        break;
      case "f": case "F": toggleFullscreen(); return;
      case "?": pause(); helpDialog.showModal(); return;
      default: return;
    }
    e.preventDefault();
  }

  // ---- steps dialog
  function buildStepsDialog() {
    const dialog = dialogShell("story-steps", "Steps");
    const list = el("div", "story-steps-list");
    const rows = [];
    const addRow = (ul, i) => {
      const li = el("li");
      const b = el("button", "story-step-row");
      b.type = "button";
      b.append(el("span", "story-step-num", String(i + 1)), el("span", "story-step-date", steps[i].date), el("span", "story-step-name", steps[i].title));
      b.addEventListener("click", () => { dialog.close(); go(i); });
      li.append(b);
      ul.append(li);
      rows[i] = b;
    };
    const chapters = story.chapters || [];
    if (chapters.length) {
      chapters.forEach((chapter, c) => {
        const end = c + 1 < chapters.length ? chapters[c + 1].first : count;
        list.append(el("h3", "story-chapter", chapter.label));
        const ul = el("ul", "story-step-list");
        for (let i = chapter.first; i < end; i++) addRow(ul, i);
        list.append(ul);
      });
    } else {
      const ul = el("ul", "story-step-list");
      for (let i = 0; i < count; i++) addRow(ul, i);
      list.append(ul);
    }
    dialog.querySelector(".story-dialog-body").append(list);
    let marked = -1;
    return {
      dialog,
      mark(i) {
        if (marked >= 0 && rows[marked]) rows[marked].removeAttribute("aria-current");
        marked = i;
        rows[i]?.setAttribute("aria-current", "step");
      },
      open() {
        dialog.showModal();
        rows[marked]?.scrollIntoView({ block: "center" });
      },
    };
  }

  function buildHelpDialog() {
    const dialog = dialogShell("story-help", "Keyboard shortcuts");
    const dl = el("dl", "story-keys");
    const keys = [
      ["← →", "Previous or next step"],
      ["Space", "Play or pause"],
      ["Home, End", "First or last step"],
      ["F", "Full screen"],
      ["?", "This list"],
      ["Esc", "Close a window"],
    ];
    for (const [key, what] of keys) {
      dl.append(el("dt", "", key), el("dd", "", what));
    }
    dialog.querySelector(".story-dialog-body").append(dl);
    return dialog;
  }

  function dialogShell(id, title) {
    const dialog = el("dialog", "story-dialog sheet");
    dialog.id = id;
    dialog.setAttribute("aria-labelledby", `${id}-title`);
    const head = el("div", "story-dialog-head");
    const h = el("h2", "", title);
    h.id = `${id}-title`;
    const close = button("Close", "xmark");
    close.addEventListener("click", () => dialog.close());
    head.append(h, close);
    dialog.append(head, el("div", "story-dialog-body"));
    dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
    return dialog;
  }

  // ---- share popover
  function buildShare() {
    const box = el("div", "story-share menu");
    box.hidden = true;
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", "Share this story");
    const copyLink = el("button", "", "Copy link to this step");
    copyLink.type = "button";
    const linkField = el("input", "form-input story-link-field");
    linkField.readOnly = true;
    linkField.hidden = true;
    linkField.setAttribute("aria-label", "Link to this step");
    const label = el("label", "form-label story-embed-label", "Embed this story");
    const code = el("textarea", "form-input story-embed-code");
    code.readOnly = true;
    code.rows = 4;
    code.id = "story-embed-code";
    label.htmlFor = code.id;
    const copyCode = el("button", "btn btn-secondary btn-small", "Copy the embed code");
    copyCode.type = "button";
    box.append(copyLink, linkField, label, code, copyCode);

    const copy = async (text, field, message) => {
      try {
        await navigator.clipboard.writeText(text);
        toast(message);
      } catch {
        field.hidden = false;
        field.value = text;
        field.focus();
        field.select();
      }
    };
    copyLink.addEventListener("click", () => copy(location.href, linkField, "Link copied"));
    copyCode.addEventListener("click", () => { code.value = snippet(); copy(code.value, code, "Code copied"); });
    return { box, code, linkField };
  }

  function snippet() {
    const frame = document.createElement("iframe");
    frame.src = story.embed_url + location.search;
    frame.width = "100%";
    frame.height = "520";
    frame.style.border = "0";
    frame.setAttribute("allow", "fullscreen");
    frame.loading = "lazy";
    frame.title = `${story.title} – History As A Map`;
    return frame.outerHTML;
  }

  function openShare() {
    pause();
    share.code.value = snippet();
    share.linkField.hidden = true;
    share.box.hidden = false;
    shareBtn.setAttribute("aria-expanded", "true");
  }

  function closeShare() {
    share.box.hidden = true;
    shareBtn.setAttribute("aria-expanded", "false");
  }

  let toastTimer = 0;
  function toast(message) {
    document.querySelector(".story-toast")?.remove();
    const t = el("div", "toast story-toast", message);
    t.setAttribute("role", "status");
    root.append(t);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.remove(), 2000);
  }
}
