// Loaded in <head> (not deferred) so the saved theme is applied before first paint.
(function () {
  var stored = null;
  try { stored = localStorage.getItem("theme"); } catch (e) { /* storage blocked */ }
  var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = stored || (prefersDark ? "dark" : "light");
})();
