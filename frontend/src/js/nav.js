export function initNav() {
  const toggle = document.querySelector(".nav-toggle");
  const menu = document.querySelector(".nav-menu");

  if (toggle && menu) {
    toggle.addEventListener("click", () => {
      menu.classList.toggle("active");
      const icon = toggle.querySelector("i");
      icon?.classList.toggle("fa-bars");
      icon?.classList.toggle("fa-times");
    });

    document.addEventListener("click", (e) => {
      if (window.innerWidth <= 768 && !e.target.closest(".navbar")) {
        menu.classList.remove("active");
        const icon = toggle.querySelector("i");
        icon?.classList.add("fa-bars");
        icon?.classList.remove("fa-times");
      }
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth > 768) {
        menu.classList.remove("active");
        const icon = toggle.querySelector("i");
        icon?.classList.add("fa-bars");
        icon?.classList.remove("fa-times");
      }
    });
  }
}

export function setActiveNav(page) {
  document.querySelectorAll(".nav-link").forEach((link) => {
    link.classList.toggle("active", link.dataset.page === page);
  });
}
