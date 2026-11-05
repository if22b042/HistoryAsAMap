// "Add an event from the main map": search approved events and pick one.
// Fills the hidden event_id input of a <form data-event-picker>.

const form = document.querySelector("form[data-event-picker]");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function formatYear(year) {
  if (year < 0) return `${-year} BC`;
  if (year < 1000) return `AD ${year}`;
  return String(year);
}

if (form) {
  const search = form.querySelector("#event-search");
  const results = form.querySelector(".event-results");
  const hidden = form.querySelector("input[name=event_id]");
  const chosen = form.querySelector(".chosen-event");
  let events = null;

  async function load() {
    if (events) return events;
    const response = await fetch("/api/events", { headers: { Accept: "application/json" } });
    events = response.ok ? await response.json() : [];
    return events;
  }

  function choose(event) {
    hidden.value = event.id;
    chosen.textContent = `Chosen: ${event.title} (${formatYear(event.year)})`;
    chosen.classList.add("chosen");
    results.replaceChildren();
    search.value = event.title;
  }

  async function render() {
    const query = search.value.trim().toLowerCase();
    if (query.length < 2) {
      results.replaceChildren();
      return;
    }
    const all = await load();
    const matches = all
      .filter((e) => `${e.title} ${e.display_year} ${e.date}`.toLowerCase().includes(query))
      .slice(0, 12);
    if (!matches.length) {
      results.replaceChildren(el("p", "form-hint", "No confirmed event matches. Add it as your own entry below."));
      return;
    }
    results.replaceChildren(...matches.map((event) => {
      const button = el("button", "event-result");
      button.type = "button";
      button.append(el("span", "year-pill", event.display_year), " ", el("span", null, event.title));
      button.addEventListener("click", () => choose(event));
      return button;
    }));
  }

  let timer;
  search.addEventListener("input", () => {
    hidden.value = "";
    chosen.textContent = "No event chosen.";
    chosen.classList.remove("chosen");
    clearTimeout(timer);
    timer = setTimeout(render, 150);
  });
  search.addEventListener("keydown", (e) => { if (e.key === "Enter") e.preventDefault(); });
}
