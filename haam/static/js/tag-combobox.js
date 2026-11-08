// Turns <select data-tag-combobox> (one official tag, e.g. "Add all events of a tag") into a
// search box with suggestions, like the map's "Filter by tag". The hidden <select> keeps the
// chosen value and is what the form submits; without JavaScript it is used as it is.

const SUGGESTIONS = 12;
const foldText = (text) => text.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
const plural = (n) => `${n.toLocaleString()} event${n === 1 ? "" : "s"}`;
let uid = 0;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function createCombobox(select) {
  const id = `tag-combo-${++uid}`;
  const tags = Array.from(select.options)
    .filter((o) => o.value && o.value !== "0" && o.dataset.name)
    .map((o) => ({
      value: o.value,
      name: o.dataset.name,
      range: o.dataset.range,
      count: Number(o.dataset.count) || 0,
      key: foldText(o.dataset.name),
    }));

  const wrapper = el("div", "tag-combo");
  const field = el("div", "tag-combo-field");
  const input = el("input", "form-input");
  input.type = "search";
  input.id = `${id}-input`;
  input.autocomplete = "off";
  input.spellcheck = false;
  input.placeholder = `Type a war, era or period – ${tags.length} tags`;
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", `${id}-list`);
  const list = el("ul", "tag-search-list tag-combo-list");
  list.id = `${id}-list`;
  list.setAttribute("role", "listbox");
  list.hidden = true;
  const chosen = el("p", "form-hint tag-combo-chosen");
  chosen.setAttribute("aria-live", "polite");
  field.append(input);
  wrapper.append(field, list, chosen);

  // The <label for=…> now points at the search box.
  const label = select.id && document.querySelector(`label[for="${select.id}"]`);
  if (label) label.htmlFor = input.id;
  select.hidden = true;
  select.after(wrapper);

  let options = [];
  let active = -1;

  function showChosen() {
    const tag = tags.find((t) => t.value === select.value);
    chosen.textContent = tag ? `Chosen: ${tag.name} (${tag.range}) · ${plural(tag.count)}` : "No tag chosen.";
    chosen.classList.toggle("chosen", Boolean(tag));
    return tag;
  }

  function close() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  }

  function choose(tag) {
    select.value = tag.value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    input.value = tag.name;
    showChosen();
    close();
  }

  function show() {
    const query = foldText(input.value.trim());
    const words = query.split(/\s+/).filter(Boolean);
    options = tags
      .filter((t) => words.every((w) => t.key.includes(w)))
      .sort((a, b) => (b.key.startsWith(query) - a.key.startsWith(query)) || b.count - a.count
        || a.name.localeCompare(b.name))
      .slice(0, SUGGESTIONS);
    active = -1;
    const items = options.map((tag, i) => {
      const li = el("li", "tag-search-option");
      li.id = `${id}-option-${i}`;
      li.setAttribute("role", "option");
      li.append(el("span", "tag-search-name", tag.name), el("span", "tag-search-meta", `${tag.range} · ${plural(tag.count)}`));
      li.addEventListener("mousedown", (e) => { e.preventDefault(); choose(tag); });
      return li;
    });
    if (!items.length) items.push(el("li", "tag-search-empty", "No matching tag – try a shorter word."));
    list.replaceChildren(...items);
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function move(step) {
    if (list.hidden) show();
    if (!options.length) return;
    active = (active + step + options.length) % options.length;
    list.querySelectorAll(".tag-search-option").forEach((li, i) => li.classList.toggle("active", i === active));
    input.setAttribute("aria-activedescendant", `${id}-option-${active}`);
    list.children[active].scrollIntoView({ block: "nearest" });
  }

  input.addEventListener("input", () => {
    // Typing again un-chooses the tag until a suggestion is picked.
    if (select.value && select.value !== "0") {
      select.value = select.options[0].value;
      showChosen();
    }
    show();
  });
  input.addEventListener("focus", () => { input.select(); show(); });
  input.addEventListener("blur", () => setTimeout(close, 120));
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter") {
      if (!list.hidden && options.length) {
        e.preventDefault();
        choose(options[Math.max(active, 0)]);
      } else if (!select.value || select.value === "0") {
        e.preventDefault(); // don't submit a half-typed tag name
      }
    } else if (e.key === "Escape" && !list.hidden) {
      e.preventDefault();
      close();
    }
  });

  const initial = showChosen(); // e.g. the form came back with an error
  if (initial) input.value = initial.name;
}

document.querySelectorAll("select[data-tag-combobox]").forEach(createCombobox);
