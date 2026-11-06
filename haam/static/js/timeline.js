// A pop-out timeline along the bottom of a Leaflet map.
//
// It lists the given events by year on a horizontal axis that always fits the
// panel (no sideways scrolling); the wheel, double-click, dragging and the
// −/+/Fit buttons zoom and pan it. Events whose labels do not fit are drawn as
// dots until you zoom in. Clicking an event calls onSelect(id) (the map flies to
// it). The axis can be given a range, e.g. the years of the selected tag. It can
// only be opened while there are at most `limit` events. Used by the main map and
// the collection map.
/* global L */

const LANE_HEIGHT = 30; // px per row of labelled events
const MAX_LANES = 6; // rows of labels; events that do not fit become dots (zoom in to read them)
const LABEL_CHARS = 22;
const ZOOM_STEP = 1.6;
const MIN_SPAN = 1; // years visible at the deepest zoom
const PAD = 18; // px left and right of the axis
const AXIS = 26; // px for the year axis at the top

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

export function formatYear(year) {
  if (year < 0) return `${-year} BC`;
  if (year < 1000) return `AD ${year}`;
  return String(year);
}

function shorten(text) {
  return text.length > LABEL_CHARS ? `${text.slice(0, LABEL_CHARS - 1)}…` : text;
}

/** A round step so that ticks are about `pixels` apart. */
function tickStep(span, width, pixels = 110) {
  const wanted = (span * pixels) / Math.max(width, 1);
  const steps = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000];
  return steps.find((s) => s >= wanted) || steps[steps.length - 1];
}

const MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
  "september", "october", "november", "december"];
const DOT_ROWS = 4;
const DOT_WIDTH = 14;

/** Where in its year an event falls (0–1): from the month and day of its date, else spread evenly. */
function positions(sorted) {
  const pos = new Map();
  const undated = new Map(); // year -> items without a month
  sorted.forEach((item) => {
    const m = /(?:(\d{1,2})\s+)?(january|february|march|april|may|june|july|august|september|october|november|december)/i
      .exec(item.label || "");
    if (m) {
      const month = MONTHS.indexOf(m[2].toLowerCase());
      const day = m[1] ? Number(m[1]) : 15;
      pos.set(item.id, item.year + (month + (day - 1) / 31) / 12);
    } else {
      if (!undated.has(item.year)) undated.set(item.year, []);
      undated.get(item.year).push(item);
    }
  });
  undated.forEach((group, year) => {
    group.forEach((item, k) => pos.set(item.id, year + (k + 0.5) / group.length));
  });
  return pos;
}

/**
 * Rows for labelled items: each goes in the first row where its label (to the
 * right of the dot, or to the left near the right edge) does not overlap; null =
 * no room left, the item is drawn as a dot instead.
 */
function assignLanes(items, left, widthOf, width) {
  const lanes = [];
  return items.map((item) => {
    const x = left(item);
    const w = widthOf(item);
    const flip = x + w > width;
    const start = flip ? x - w : x;
    const end = flip ? x : x + w;
    let lane = lanes.findIndex((spans) => spans.every(([a, b]) => end + 6 <= a || start >= b + 6));
    if (lane === -1 && lanes.length < MAX_LANES) {
      lane = lanes.length;
      lanes.push([]);
    }
    if (lane === -1) return null;
    lanes[lane].push([start, end]);
    return { lane, flip };
  });
}

/** Rows for the dots: the first of DOT_ROWS rows where the dot does not touch another. */
function assignDotRows(xs) {
  const ends = Array(DOT_ROWS).fill(-Infinity);
  return xs.map((x) => {
    let row = ends.findIndex((end) => x - DOT_WIDTH / 2 >= end);
    if (row === -1) row = ends.indexOf(Math.min(...ends)); // all rows busy: overlap the oldest
    ends[row] = x + DOT_WIDTH / 2;
    return row;
  });
}

function button(className, text, label) {
  const node = el("button", className, text);
  node.type = "button";
  node.title = label;
  node.setAttribute("aria-label", label);
  return node;
}

/**
 * @param {object} options
 * @param {L.Map} options.map
 * @param {(id: number) => void} options.onSelect
 * @param {number} [options.limit] most events the timeline can show
 * @param {(item) => string|null} [options.colorFor] dot colour; null = category colour
 */
export function createTimeline({ map, onSelect, limit = 150, colorFor = () => null }) {
  const container = map.getContainer();
  let items = [];
  let open = false;
  let activeId = null;
  // Years the axis covers (full) and the zoomed part that is shown (view).
  let full = { from: 0, to: 1 };
  let view = { from: 0, to: 1 };
  let rangeLabel = "";

  const toggle = el("button", "timeline-toggle btn btn-secondary");
  toggle.type = "button";
  toggle.setAttribute("aria-expanded", "false");
  toggle.append(el("i", "fas fa-stream"), el("span", null, " Timeline"));
  toggle.firstChild.setAttribute("aria-hidden", "true");

  const panel = el("section", "timeline-panel");
  panel.hidden = true;
  panel.setAttribute("aria-label", "Timeline of the events shown");
  const header = el("div", "timeline-header");
  const heading = el("strong", "timeline-heading", "Timeline");
  const tools = el("div", "timeline-tools");
  const viewLabel = el("span", "timeline-view");
  const zoomOut = button("icon-btn timeline-zoom", "−", "Zoom out");
  const zoomIn = button("icon-btn timeline-zoom", "+", "Zoom in");
  const fit = button("btn btn-secondary btn-small", "Fit", "Show the whole range");
  const close = button("icon-btn timeline-close", null, "Close timeline");
  close.append(el("i", "fas fa-times"));
  tools.append(viewLabel, zoomOut, zoomIn, fit, close);
  header.append(heading, tools);
  const scroller = el("div", "timeline-scroller");
  const track = el("div", "timeline-track");
  const hint = el("p", "timeline-hint");
  scroller.append(track);
  panel.append(header, scroller, hint);

  container.append(toggle, panel);
  [toggle, panel].forEach((node) => {
    L.DomEvent.disableClickPropagation(node);
    L.DomEvent.disableScrollPropagation(node);
  });

  function setOpen(value) {
    open = value && items.length > 0 && items.length <= limit;
    panel.hidden = !open;
    toggle.hidden = open;
    toggle.setAttribute("aria-expanded", String(open));
    document.body.classList.toggle("timeline-open", open);
    container.classList.toggle("has-timeline", open);
    if (open) render();
    liftControls();
  }

  /** Move the map's bottom controls (zoom, legend, attribution) above the open panel. */
  function liftControls() {
    container.style.setProperty("--timeline-height", open ? `${panel.offsetHeight}px` : "0px");
  }

  const innerWidth = () => Math.max(track.clientWidth - 2 * PAD, 100);
  const yearAt = (clientX) => {
    const left = track.getBoundingClientRect().left + PAD;
    return view.from + ((clientX - left) / innerWidth()) * (view.to - view.from);
  };

  function setView(from, span) {
    const width = Math.min(Math.max(span, MIN_SPAN), full.to - full.from);
    const start = Math.min(Math.max(from, full.from), full.to - width);
    view = { from: start, to: start + width };
    render();
  }

  /** Zoom by `factor` (<1 = in), keeping the year `around` at the same place. */
  function zoom(factor, around = (view.from + view.to) / 2) {
    const span = view.to - view.from;
    const next = span * factor;
    const ratio = (around - view.from) / (span || 1);
    setView(around - ratio * next, next);
  }

  const pan = (years) => setView(view.from + years, view.to - view.from);

  toggle.addEventListener("click", () => setOpen(true));
  close.addEventListener("click", () => setOpen(false));
  zoomIn.addEventListener("click", () => zoom(1 / ZOOM_STEP));
  zoomOut.addEventListener("click", () => zoom(ZOOM_STEP));
  fit.addEventListener("click", () => setView(full.from, full.to - full.from));
  panel.addEventListener("keydown", (e) => {
    if (e.key === "Escape") setOpen(false);
    else if (e.key === "+" || e.key === "=") zoom(1 / ZOOM_STEP);
    else if (e.key === "-") zoom(ZOOM_STEP);
    else if (e.key === "ArrowLeft" && e.target === track) pan(-(view.to - view.from) / 5);
    else if (e.key === "ArrowRight" && e.target === track) pan((view.to - view.from) / 5);
  });
  track.tabIndex = 0;
  track.setAttribute("aria-label", "Timeline axis: + and − zoom, arrow keys move");

  track.addEventListener("wheel", (e) => {
    e.preventDefault();
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      pan((e.deltaX / innerWidth()) * (view.to - view.from)); // sideways swipe on a touchpad
    } else {
      zoom(e.deltaY < 0 ? 1 / 1.25 : 1.25, yearAt(e.clientX));
    }
  }, { passive: false });
  track.addEventListener("dblclick", (e) => {
    if (!e.target.closest(".timeline-item")) zoom(1 / ZOOM_STEP, yearAt(e.clientX));
  });

  let drag = null;
  track.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest(".timeline-item")) return;
    drag = { x: e.clientX, from: view.from };
    track.setPointerCapture(e.pointerId);
    track.classList.add("dragging");
  });
  track.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const span = view.to - view.from;
    setView(drag.from + ((drag.x - e.clientX) / innerWidth()) * span, span);
  });
  const endDrag = () => {
    drag = null;
    track.classList.remove("dragging");
  };
  track.addEventListener("pointerup", endDrag);
  track.addEventListener("pointercancel", endDrag);

  function updateToggle() {
    const usable = items.length > 0 && items.length <= limit;
    toggle.disabled = !usable;
    toggle.title = usable
      ? `Show the ${items.length} events on a timeline`
      : items.length
        ? `The timeline shows up to ${limit} events: narrow the filters (now ${items.length})`
        : "No events to show";
    toggle.lastChild.textContent = usable ? ` Timeline (${items.length})` : ` Timeline (max ${limit})`;
  }

  function render() {
    const sorted = [...items].sort((a, b) => a.year - b.year || a.title.localeCompare(b.title));
    const count = sorted.length === 1 ? "1 event" : `${sorted.length} events`;
    const first = Math.floor(full.from);
    const last = Math.ceil(full.to) - 1;
    const range = last > first ? `${formatYear(first)} – ${formatYear(last)}` : formatYear(first);
    heading.textContent = `Timeline · ${count} · ${rangeLabel ? `${rangeLabel}, ` : ""}${range}`;

    const zoomed = view.from > full.from + 0.01 || view.to < full.to - 0.01;
    viewLabel.textContent = zoomed
      ? `Showing ${formatYear(Math.floor(view.from))} – ${formatYear(Math.ceil(view.to) - 1)}`
      : "";
    fit.disabled = !zoomed;
    zoomOut.disabled = !zoomed;
    zoomIn.disabled = view.to - view.from <= MIN_SPAN + 1e-9;

    const inner = innerWidth();
    const width = inner + 2 * PAD;
    const viewSpan = Math.max(view.to - view.from, 1e-9);
    // Years are whole numbers; an event sits inside its year by date (see positions()).
    const x = (year) => PAD + ((year - view.from) / viewSpan) * inner;
    const pos = positions(sorted);
    const at = (item) => x(pos.get(item.id));
    const shown = sorted.filter((item) => {
      const p = pos.get(item.id);
      return p >= view.from - 1e-6 && p <= view.to + 1e-6;
    }).sort((a, b) => pos.get(a.id) - pos.get(b.id));
    const widthOf = (item) => 22 + Math.min(item.title.length, LABEL_CHARS) * 6.6;
    const lanes = assignLanes(shown, at, widthOf, width);
    const rows = Math.max(1, ...lanes.filter(Boolean).map((l) => l.lane + 1));
    const dotItems = shown.filter((_, i) => lanes[i] === null);
    const dotRows = new Map(assignDotRows(dotItems.map(at)).map((row, i) => [dotItems[i].id, row]));
    const dots = dotItems.length;
    const usedDotRows = dots ? Math.max(...dotRows.values()) + 1 : 0;
    const dotTop = rows * LANE_HEIGHT + 2;

    const nodes = [];
    const axis = el("div", "timeline-axis");
    const step = tickStep(viewSpan, inner);
    let ticks = [];
    for (let year = Math.ceil(view.from / step) * step; year <= view.to; year += step) {
      if (year !== 0) ticks.push(year); // there is no year 0
    }
    if (ticks.length < 2) {
      ticks = [...new Set([Math.ceil(view.from), Math.floor(view.to)])].filter((y) => y !== 0);
    }
    ticks.forEach((year) => {
      const tick = el("span", "timeline-tick", formatYear(year));
      tick.style.left = `${x(year)}px`;
      axis.append(tick);
    });
    nodes.push(axis);

    shown.forEach((item, i) => {
      const node = el("button", "timeline-item");
      node.type = "button";
      node.dataset.id = item.id;
      const left = at(item);
      node.style.left = `${left}px`;
      const label = `${item.title} · ${item.label || formatYear(item.year)}`;
      node.title = label;
      node.setAttribute("aria-label", label);
      const dot = el("span", `timeline-dot dot dot-${item.category}`);
      const color = colorFor(item);
      if (color) dot.style.background = color;
      node.append(dot);
      if (lanes[i] === null) {
        node.classList.add("timeline-item-dot");
        node.style.top = `${AXIS + dotTop + dotRows.get(item.id) * 16}px`;
      } else {
        node.style.top = `${AXIS + lanes[i].lane * LANE_HEIGHT}px`;
        node.append(el("span", "timeline-label", shorten(item.title)));
        // Near the right edge the label goes to the left of its dot.
        if (lanes[i].flip) node.classList.add("timeline-item-flip");
      }
      if (item.id === activeId) node.classList.add("active");
      node.addEventListener("click", () => {
        setActive(item.id);
        onSelect(item.id);
      });
      nodes.push(node);
    });

    track.style.height = `${(dots ? dotTop + usedDotRows * 16 + 4 : rows * LANE_HEIGHT) + 26}px`;
    track.replaceChildren(...nodes);
    hint.textContent = dots
      ? `${dots} more event${dots === 1 ? "" : "s"} shown as dots – zoom in (wheel, double-click or +) to read them; drag to move.`
      : "Wheel or double-click to zoom, drag to move.";
    liftControls();
  }

  function setActive(id) {
    activeId = id;
    track.querySelectorAll(".timeline-item").forEach((node) => {
      node.classList.toggle("active", Number(node.dataset.id) === id);
    });
  }

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (open) render(); }, 150);
  });

  return {
    /**
     * Replace the events: [{id, year, title, label, category}]. `range` ({from, to,
     * label}) makes the axis cover at least those years, e.g. the selected tag's.
     */
    update(next, range = null) {
      items = next;
      const years = items.map((item) => item.year);
      let from = Math.min(...years, range ? range.from : Infinity);
      // The axis runs to the end of the last year (events sit inside their year).
      let to = Math.max(...years, range ? range.to : -Infinity) + 1;
      if (!Number.isFinite(from)) {
        from = 0;
        to = 1;
      }
      if (to - from < MIN_SPAN) {
        from -= MIN_SPAN / 2;
        to += MIN_SPAN / 2;
      }
      if (from !== full.from || to !== full.to) view = { from, to }; // a new range: show all of it
      full = { from, to };
      rangeLabel = range && range.label ? range.label : "";
      updateToggle();
      if (open) {
        if (items.length === 0 || items.length > limit) setOpen(false);
        else render();
      }
    },
    setActive,
    get isOpen() { return open; },
  };
}
