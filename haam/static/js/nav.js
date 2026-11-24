// Mobile menu and dark-mode toggle, used on every page.
(function () {
  const root = document.documentElement;
  const toggle = document.querySelector(".nav-toggle");
  const menu = document.getElementById("nav-menu");

  function setMenu(open, returnFocus) {
    menu.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    if (open) {
      const first = menu.querySelector("a, button");
      if (first) first.focus();
    } else if (returnFocus) {
      toggle.focus();
    }
  }

  if (toggle && menu) {
    toggle.addEventListener("click", () => {
      const open = !menu.classList.contains("open");
      setMenu(open, !open);
    });
    document.addEventListener("click", (e) => {
      if (menu.classList.contains("open") && !e.target.closest(".navbar")) setMenu(false, false);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && menu.classList.contains("open")) setMenu(false, true);
    });
  }

  const themeButton = document.querySelector(".theme-toggle");
  function showTheme() {
    themeButton.setAttribute("aria-pressed", String(root.dataset.theme === "dark"));
  }
  if (themeButton) {
    showTheme();
    themeButton.addEventListener("click", () => {
      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
      try { localStorage.setItem("theme", root.dataset.theme); } catch (e) { /* ignore */ }
      showTheme();
      document.dispatchEvent(new CustomEvent("themechange"));
    });
  }
})();
