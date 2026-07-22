import "../css/base.css";
import "../css/forms.css";
import { previewEvent } from "./api.js";
import { initNav, setActiveNav } from "./nav.js";

const CATEGORIES = [
  "military",
  "diplomatic",
  "naval",
  "political",
  "economic",
  "cultural",
  "scientific",
  "other",
];

function showError(message) {
  const el = document.getElementById("form-error");
  el.textContent = message;
  el.hidden = false;
}

async function handleSubmit(e) {
  e.preventDefault();
  const wikiLink = document.getElementById("wikiLink").value.trim();
  const category = document.getElementById("category").value;
  const errorEl = document.getElementById("form-error");
  errorEl.hidden = true;

  try {
    const preview = await previewEvent(wikiLink);
    sessionStorage.setItem(
      "haam_preview",
      JSON.stringify({ ...preview, category })
    );
    window.location.href = "/preview.html";
  } catch (err) {
    showError(err.message);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initNav();
  setActiveNav("add");

  const select = document.getElementById("category");
  CATEGORIES.forEach((cat) => {
    const option = document.createElement("option");
    option.value = cat;
    option.textContent = cat.charAt(0).toUpperCase() + cat.slice(1);
    select.appendChild(option);
  });

  document.getElementById("add-event-form").addEventListener("submit", handleSubmit);
});
