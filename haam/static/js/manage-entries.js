// The entry list on a collection's manage page: remove (one or many), reorder (drag or arrow
// buttons) and filter without reloading the page. Every button is also a plain form button
// (form="entry-actions" + formaction), so without JavaScript the same actions reload the page.

const form = document.getElementById("entry-actions");
const list = document.querySelector("[data-entries]");

const foldText = (text) => text.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();

if (form && list) {
  const csrf = form.querySelector("input[name=csrf_token]")?.value || "";
  const orderUrl = form.dataset.orderUrl;
  const filter = document.querySelector("[data-entries-filter]");
  const status = document.querySelector("[data-entries-status]");
  const countEl = document.querySelector("[data-entry-count]");
  const emptyEl = document.querySelector("[data-entries-empty]");
  const toolbar = document.querySelector("[data-entries-toolbar]");
  const removeSelected = document.querySelector("[data-remove-selected]");
  const selectedCount = document.querySelector("[data-selected-count]");

  const rows = () => Array.from(list.children);
  const visibleRows = () => rows().filter((row) => !row.hidden);
  const checkbox = (row) => row.querySelector(".entry-check");
  const checkedRows = () => rows().filter((row) => checkbox(row).checked);
  const titleOf = (row) => row.querySelector(".entry-body strong").textContent;

  // Show the parts that only work with JavaScript.
  document.querySelectorAll("[data-entries-filter], [data-select-buttons], [data-entries-hint], .drag-handle")
    .forEach((node) => { node.hidden = false; });

  let statusTimer;
  function say(message, kind = "") {
    clearTimeout(statusTimer);
    status.textContent = message;
    status.className = `entries-status ${kind}`;
    if (kind !== "error") statusTimer = setTimeout(() => { status.textContent = ""; }, 4000);
  }

  async function post(url, ids = [], extra = {}) {
    const body = new FormData();
    body.append("csrf_token", csrf);
    ids.forEach((id) => body.append("entry_id", id));
    Object.entries(extra).forEach(([key, value]) => body.append(key, value));
    let response;
    try {
      response = await fetch(url, {
        method: "POST", body, credentials: "same-origin", headers: { Accept: "application/json" },
      });
    } catch {
      throw new Error("No connection – nothing was changed. Try again.");
    }
    let data = {};
    try { data = await response.json(); } catch { /* e.g. the CSRF error page */ }
    if (!response.ok) {
      throw new Error(data.error || (response.status === 400
        ? "This page has expired – reload it and try again."
        : `Something went wrong (error ${response.status}). Reload the page and try again.`));
    }
    return data;
  }

  /** Numbers, counts and button states after any change. The numbers match the map's markers. */
  function refresh(count) {
    const all = rows();
    all.forEach((row, i) => { row.querySelector("[data-number]").textContent = `${i + 1}.`; });
    countEl.textContent = count ?? all.length;
    emptyEl.hidden = all.length > 0;
    if (toolbar) toolbar.hidden = all.length === 0;
    const selected = checkedRows().length;
    selectedCount.textContent = selected ? ` (${selected})` : "";
    removeSelected.disabled = selected === 0;
    if (filter && filter.value.trim()) {
      const shown = visibleRows().length;
      filter.title = `${shown} of ${all.length} shown`;
    }
  }

  // ------------------------------------------------------------ remove
  function dropRows(ids) {
    const gone = new Set(ids.map(String));
    const all = rows();
    const lastIndex = all.findLastIndex((row) => gone.has(row.dataset.id));
    // Keep the keyboard where it was: the next remaining row (or the one before).
    const next = all.slice(lastIndex + 1).find((row) => !gone.has(row.dataset.id) && !row.hidden)
      || all.slice(0, lastIndex).reverse().find((row) => !gone.has(row.dataset.id) && !row.hidden);
    all.filter((row) => gone.has(row.dataset.id)).forEach((row) => row.remove());
    return next;
  }

  async function removeRows(targetRows, url) {
    const ids = targetRows.map((row) => row.dataset.id);
    targetRows.forEach((row) => row.classList.add("is-busy"));
    try {
      const data = await post(url, url === form.action ? ids : []);
      const next = dropRows(data.removed || ids);
      refresh(data.count);
      say(data.message || "Removed.", "success");
      (next?.querySelector("[data-remove]") || filter)?.focus({ preventScroll: true });
    } catch (error) {
      targetRows.forEach((row) => row.classList.remove("is-busy"));
      say(error.message, "error");
    }
  }

  // ------------------------------------------------------------ order
  let saving = false;
  let saveAgain = false;
  let savedOrder = rows().map((row) => row.dataset.id).join(",");

  async function saveOrder() {
    const order = rows().map((row) => row.dataset.id);
    if (order.join(",") === savedOrder) return;
    if (saving) { saveAgain = true; return; }
    saving = true;
    say("Saving the order…");
    try {
      await post(orderUrl, order);
      savedOrder = order.join(",");
      say("Order saved.", "success");
    } catch (error) {
      say(error.message, "error");
    } finally {
      saving = false;
      if (saveAgain) { saveAgain = false; saveOrder(); }
    }
  }

  function moveRow(row, step) {
    // Skip rows hidden by the filter, so the arrows move past what you can see.
    let other = row;
    do { other = step < 0 ? other.previousElementSibling : other.nextElementSibling; } while (other && other.hidden);
    if (!other) return false;
    if (step < 0) other.before(row);
    else other.after(row);
    return true;
  }

  // ------------------------------------------------------------ buttons
  form.addEventListener("submit", (event) => {
    const button = event.submitter;
    if (!button) return;
    event.preventDefault();
    const row = button.closest(".manage-entry");

    if (button.matches("[data-move]")) {
      if (moveRow(row, Number(button.dataset.move))) {
        refresh();
        row.scrollIntoView({ block: "nearest" });
        saveOrder();
      }
      button.focus({ preventScroll: true });
    } else if (button.matches("[data-remove]")) {
      // Main-map events are easy to add again; your own entries are not.
      if (row.hasAttribute("data-custom") && !window.confirm(`Remove your entry “${titleOf(row)}”? It cannot be restored.`)) return;
      removeRows([row], button.formAction);
    } else if (button.matches("[data-remove-selected]")) {
      const chosen = checkedRows();
      if (!chosen.length) { say("Tick the entries to remove first.", "error"); return; }
      const hiddenToo = chosen.some((r) => r.hidden) ? " (some are hidden by the filter)" : "";
      const question = chosen.length === 1
        ? `Remove “${titleOf(chosen[0])}”${hiddenToo}?`
        : `Remove ${chosen.length} entries${hiddenToo}?`;
      if (window.confirm(question)) removeRows(chosen, form.action);
    }
  });

  // ------------------------------------------------------------ selection
  let lastClicked = null;
  list.addEventListener("click", (event) => {
    const box = event.target.closest(".entry-check");
    if (!box) return;
    // Shift-click ticks (or unticks) every shown entry between this one and the last one clicked.
    if (event.shiftKey && lastClicked && lastClicked !== box && lastClicked.isConnected) {
      const shown = visibleRows().map(checkbox);
      const [a, b] = [shown.indexOf(lastClicked), shown.indexOf(box)].sort((x, y) => x - y);
      if (a >= 0) shown.slice(a, b + 1).forEach((c) => { c.checked = box.checked; });
    }
    lastClicked = box;
    refresh();
  });
  list.addEventListener("change", () => refresh());

  document.querySelectorAll("[data-select]").forEach((button) => {
    button.addEventListener("click", () => {
      const mode = button.dataset.select;
      if (mode === "none") rows().forEach((row) => { checkbox(row).checked = false; });
      else visibleRows().forEach((row) => {
        const box = checkbox(row);
        box.checked = mode === "all" ? true : !box.checked;
      });
      refresh();
    });
  });

  // ------------------------------------------------------------ filter
  rows().forEach((row) => { row.dataset.key = foldText(row.dataset.search || ""); });
  filter?.addEventListener("input", () => {
    const words = foldText(filter.value.trim()).split(/\s+/).filter(Boolean);
    rows().forEach((row) => {
      row.dataset.key ??= foldText(row.dataset.search || "");
      row.hidden = !words.every((w) => row.dataset.key.includes(w));
    });
    const shown = visibleRows().length;
    say(words.length ? `${shown} of ${rows().length} entries shown.` : "");
    refresh();
  });
  filter?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") e.preventDefault();
    if (e.key === "Escape" && filter.value) { filter.value = ""; filter.dispatchEvent(new Event("input")); }
  });

  // ------------------------------------------------------------ drag and drop
  let dragged = null;
  list.addEventListener("pointerdown", (event) => {
    const handle = event.target.closest(".drag-handle");
    if (handle) handle.closest(".manage-entry").draggable = true;
  });
  list.addEventListener("pointerup", (event) => {
    const row = event.target.closest(".manage-entry");
    if (row && row !== dragged) row.draggable = false;
  });
  list.addEventListener("dragstart", (event) => {
    dragged = event.target.closest(".manage-entry");
    if (!dragged) return;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", dragged.dataset.id); // Firefox needs some data
    requestAnimationFrame(() => dragged?.classList.add("is-dragging"));
  });
  list.addEventListener("dragover", (event) => {
    if (!dragged) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    const over = event.target.closest(".manage-entry");
    if (!over || over === dragged) return;
    const box = over.getBoundingClientRect();
    if (event.clientY < box.top + box.height / 2) over.before(dragged);
    else over.after(dragged);
  });
  list.addEventListener("drop", (event) => { if (dragged) event.preventDefault(); });
  list.addEventListener("dragend", () => {
    if (!dragged) return;
    dragged.classList.remove("is-dragging");
    dragged.draggable = false;
    dragged = null;
    refresh();
    saveOrder();
  });

  refresh();
}
