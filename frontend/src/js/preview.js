import "../css/base.css";
import "../css/forms.css";
import { createEvent } from "./api.js";
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

function enableEdit(fieldId) {
  const field = document.getElementById(fieldId);
  if (field.tagName === "SELECT") {
    field.disabled = false;
  } else {
    field.removeAttribute("readonly");
  }
  field.focus();
  document.getElementById("modified").value = "true";
}

window.enableEdit = enableEdit;

function populateCategorySelect(selected) {
  const select = document.getElementById("category");
  select.innerHTML = '<option value="">Select a category...</option>';
  CATEGORIES.forEach((cat) => {
    const option = document.createElement("option");
    option.value = cat;
    option.textContent = cat.charAt(0).toUpperCase() + cat.slice(1);
    option.selected = cat === selected;
    select.appendChild(option);
  });
}

function loadPreviewData() {
  const raw = sessionStorage.getItem("haam_preview");
  if (!raw) {
    window.location.href = "/add-event.html";
    return null;
  }
  return JSON.parse(raw);
}

async function handleSubmit(e) {
  e.preventDefault();

  const category = document.getElementById("category").value;
  if (!category) {
    document.getElementById("form-error").textContent = "Event category is required.";
    document.getElementById("form-error").hidden = false;
    return;
  }

  const payload = {
    title: document.getElementById("title").value.trim(),
    date: document.getElementById("date").value.trim(),
    year: parseInt(document.getElementById("year").value, 10),
    first_paragraph: document.getElementById("first_paragraph").value.trim(),
    link: document.getElementById("link").value.trim(),
    category,
    lat: parseFloat(document.getElementById("lat").value),
    lon: parseFloat(document.getElementById("lon").value),
    modified: document.getElementById("modified").value === "true",
  };

  try {
    await createEvent(payload);
    sessionStorage.removeItem("haam_preview");
    document.getElementById("preview-form").hidden = true;
    document.getElementById("success-message").hidden = false;
  } catch (err) {
    document.getElementById("form-error").textContent = err.message;
    document.getElementById("form-error").hidden = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initNav();
  setActiveNav("add");

  const data = loadPreviewData();
  if (!data) return;

  document.getElementById("title").value = data.title || "";
  document.getElementById("date").value = data.date || "";
  document.getElementById("year").value = data.year || "";
  document.getElementById("first_paragraph").value = data.first_paragraph || "";
  document.getElementById("link").value = data.link || "";
  document.getElementById("lat").value = data.lat ?? "";
  document.getElementById("lon").value = data.lon ?? "";

  populateCategorySelect(data.category || "");
  document.getElementById("preview-form").addEventListener("submit", handleSubmit);
});
