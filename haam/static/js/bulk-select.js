// Review queue: select-all, a count, and a confirmation before a bulk action.
(() => {
  const form = document.getElementById("bulk-form");
  if (!form) return;
  const all = document.getElementById("select-all");
  const checks = () => Array.from(document.querySelectorAll(".bulk-check"));
  const count = form.querySelector(".bulk-count");
  const update = () => {
    const n = checks().filter((c) => c.checked).length;
    count.textContent = n ? `${n} selected` : "";
    all.checked = n > 0 && n === checks().length;
  };
  all.addEventListener("change", () => { checks().forEach((c) => { c.checked = all.checked; }); update(); });
  document.addEventListener("change", (e) => { if (e.target.classList.contains("bulk-check")) update(); });
  form.addEventListener("submit", (e) => {
    const n = checks().filter((c) => c.checked).length;
    const message = e.submitter && e.submitter.dataset.bulkConfirm;
    if (n === 0) { e.preventDefault(); window.alert("Select at least one event first."); return; }
    if (message && !window.confirm(message.replace("{n}", n))) e.preventDefault();
  });
})();
