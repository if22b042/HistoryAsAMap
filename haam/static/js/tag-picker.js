// Turns <select multiple data-tag-picker> into searchable, clickable tag pills.
// Without JavaScript the plain multi-select still works.

function createPicker(select) {
  const wrapper = document.createElement("div");
  wrapper.className = "tag-picker";

  const search = document.createElement("input");
  search.type = "search";
  search.className = "form-input";
  search.placeholder = "Search tags…";
  search.setAttribute("aria-label", "Search tags");

  const chosen = document.createElement("div");
  chosen.className = "tag-picker-chosen";
  chosen.setAttribute("aria-live", "polite");

  const list = document.createElement("div");
  list.className = "tag-picker-list";

  wrapper.append(chosen, search, list);
  select.hidden = true;
  const hint = select.nextElementSibling;
  if (hint && hint.matches(".form-hint")) hint.hidden = true; // the "hold Ctrl" hint
  select.after(wrapper);

  const options = Array.from(select.options);

  function pill(option, removable) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tag-pill" + (option.selected ? " selected" : "") +
      (option.hasAttribute("data-suggested") ? " suggested" : "");
    button.textContent = option.textContent;
    button.setAttribute("aria-pressed", String(option.selected));
    if (removable) button.title = "Remove";
    button.addEventListener("click", () => {
      option.selected = !option.selected;
      render();
    });
    return button;
  }

  function render() {
    const query = search.value.trim().toLowerCase();
    chosen.replaceChildren(...options.filter((o) => o.selected).map((o) => pill(o, true)));
    if (!chosen.children.length) {
      const empty = document.createElement("span");
      empty.className = "form-hint";
      empty.textContent = "No tags selected.";
      chosen.append(empty);
    }
    const matches = options.filter((o) => !o.selected && o.textContent.toLowerCase().includes(query));
    // Suggested tags (covering the event's year) first; cap the list for long catalogues.
    const shown = query ? matches.slice(0, 60) : matches.filter((o) => o.hasAttribute("data-suggested")).slice(0, 40);
    list.replaceChildren(...shown.map((o) => pill(o, false)));
    if (!shown.length) {
      const hint = document.createElement("span");
      hint.className = "form-hint";
      hint.textContent = query ? "No matching tags." : "Type to search all tags.";
      list.append(hint);
    }
  }

  search.addEventListener("input", render);
  search.addEventListener("keydown", (e) => { if (e.key === "Enter") e.preventDefault(); });
  render();
}

document.querySelectorAll("select[data-tag-picker]").forEach(createPicker);
