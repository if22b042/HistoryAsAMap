// Mobile menu and dark-mode toggle, used on every page.
(function () {
  const root = document.documentElement;
  const toggle = document.querySelector(".nav-toggle");
  const menu = document.getElementById("nav-menu");

  function setMenu(open) {
    menu.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    const icon = toggle.querySelector("i");
    icon.classList.toggle("fa-bars", !open);
    icon.classList.toggle("fa-times", open);
  }

  if (toggle && menu) {
    toggle.addEventListener("click", () => setMenu(!menu.classList.contains("open")));
    document.addEventListener("click", (e) => {
      if (menu.classList.contains("open") && !e.target.closest(".navbar")) setMenu(false);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && menu.classList.contains("open")) setMenu(false);
    });
  }

  const themeButton = document.querySelector(".theme-toggle");
  function showThemeIcon() {
    const icon = themeButton.querySelector("i");
    const dark = root.dataset.theme === "dark";
    icon.classList.toggle("fa-sun", dark);
    icon.classList.toggle("fa-moon", !dark);
  }
  if (themeButton) {
    showThemeIcon();
    themeButton.addEventListener("click", () => {
      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
      try { localStorage.setItem("theme", root.dataset.theme); } catch (e) { /* ignore */ }
      showThemeIcon();
      document.dispatchEvent(new CustomEvent("themechange"));
    });
  }
})();
