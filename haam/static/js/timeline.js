// A pop-out timeline along the bottom of a Leaflet map.
//
// It lists the given events by year on a horizontal axis; clicking one calls
// onSelect(id) (the map then flies to it). It can only be opened while there
// are at most `limit` events, so it stays readable. Used by the main map and the
// collection map.
/* global L */

const LANE_HEIGHT = 30; // px per row of events
const MAX_LANES = 9; // rows before the axis is stretched (and scrolls sideways)
const LABEL_CHARS = 22;

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

/** Put each item in the first row where it does not overlap the previous one. */
function assignLanes(items, x, widthOf) {
  const laneEnds = [];
  return items.map((item) => {
    const left = x(item.year);
    let lane = laneEnds.findIndex((end) => end <= left);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(0);
    }
    laneEnds[lane] = left + widthOf(item) + 6;
    return lane;
  });
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
  const close = el("button", "icon-btn timeline-close");
  close.type = "button";
  close.setAttribute("aria-label", "Close timeline");
  close.append(el("i", "fas fa-times"));
  header.append(heading, close);
  const scroller = el("div", "timeline-scroller");
  const track = el("div", "timeline-track");
  scroller.append(track);
  panel.append(header, scroller);

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

  toggle.addEventListener("click", () => setOpen(true));
  close.addEventListener("click", () => setOpen(false));
  panel.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
  // A normal mouse wheel scrolls the timeline sideways once it is wider than the panel.
  scroller.addEventListener("wheel", (e) => {
    const sideways = scroller.scrollWidth > scroller.clientWidth;
    const upDown = scroller.scrollHeight > scroller.clientHeight;
    if (sideways && !upDown && Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
      scroller.scrollLeft += e.deltaY;
      e.preventDefault();
    }
  }, { passive: false });

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
    const from = sorted[0].year;
    const to = sorted[sorted.length - 1].year;
    const span = Math.max(to - from, 1);
    const count = sorted.length === 1 ? "1 event" : `${sorted.length} events`;
    heading.textContent = from === to
      ? `Timeline · ${count} in ${formatYear(from)}`
      : `Timeline · ${count}, ${formatYear(from)} – ${formatYear(to)}`;

    const pad = 16;
    const widthOf = (item) => 22 + Math.min(item.title.length, LABEL_CHARS) * 6.6;
    const visible = Math.max(scroller.clientWidth, 300);
    // Stretch the axis until the events fit in MAX_LANES rows (then it scrolls sideways).
    let width = visible;
    let lanes;
    for (let attempt = 0; attempt < 8; attempt++) {
      const inner = width - 2 * pad - 180; // room for the last label
      const x = (year) => pad + ((year - from) / span) * inner;
      lanes = assignLanes(sorted, x, widthOf);
      if (Math.max(...lanes) < MAX_LANES) break;
      width *= 1.35;
    }
    const inner = width - 2 * pad - 180;
    const x = (year) => pad + ((year - from) / span) * inner;
    const rows = Math.max(...lanes) + 1;

    const nodes = [];
    const axis = el("div", "timeline-axis");
    const step = tickStep(span, inner);
    for (let year = Math.ceil(from / step) * step; year <= to; year += step) {
      const tick = el("span", "timeline-tick", formatYear(year === 0 ? 1 : year));
      tick.style.left = `${x(year)}px`;
      axis.append(tick);
    }
    nodes.push(axis);

    sorted.forEach((item, i) => {
      const button = el("button", "timeline-item");
      button.type = "button";
      button.dataset.id = item.id;
      button.style.left = `${x(item.year)}px`;
      button.style.top = `${lanes[i] * LANE_HEIGHT}px`;
      button.title = `${item.title} · ${item.label || formatYear(item.year)}`;
      button.setAttribute("aria-label", `${item.title}, ${item.label || formatYear(item.year)}`);
      const dot = el("span", `timeline-dot dot dot-${item.category}`);
      const color = colorFor(item);
      if (color) dot.style.background = color;
      button.append(dot, el("span", "timeline-label", shorten(item.title)));
      if (item.id === activeId) button.classList.add("active");
      button.addEventListener("click", () => {
        setActive(item.id);
        onSelect(item.id);
      });
      nodes.push(button);
    });

    track.style.width = `${width}px`;
    track.style.height = `${rows * LANE_HEIGHT + 26}px`;
    track.replaceChildren(...nodes);
    liftControls();
  }

  function setActive(id) {
    activeId = id;
    track.querySelectorAll(".timeline-item").forEach((node) => {
      const isActive = Number(node.dataset.id) === id;
      node.classList.toggle("active", isActive);
      if (isActive) node.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
  }

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (open) render(); }, 150);
  });

  return {
    /** Replace the events: [{id, year, title, label, category}]. */
    update(next) {
      items = next;
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
