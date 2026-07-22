import "../css/base.css";
import "../css/forms.css";
import "../css/admin.css";
import {
  approveEvent,
  fetchPendingEvents,
  rejectEvent,
} from "./api.js";
import { initNav, setActiveNav } from "./nav.js";

const ADMIN_KEY_STORAGE = "haam_admin_key";

function getAdminKey() {
  return localStorage.getItem(ADMIN_KEY_STORAGE) || "";
}

function saveAdminKey(key) {
  localStorage.setItem(ADMIN_KEY_STORAGE, key);
}

function renderPending(events) {
  const container = document.getElementById("pending-list");

  if (!events.length) {
    container.innerHTML = '<p class="empty-state">No pending events to review.</p>';
    return;
  }

  container.innerHTML = events
    .map(
      (event) => `
      <article class="admin-card" data-id="${event.id}">
        <h3>${event.title}</h3>
        <div class="admin-card-meta">
          ${event.year} · ${event.category} ·
          ${event.location ? `${event.location.lat.toFixed(4)}, ${event.location.lon.toFixed(4)}` : "No location"}
        </div>
        <p>${event.first_paragraph}</p>
        <a href="${event.link}" target="_blank" rel="noopener">Wikipedia article</a>
        <div class="admin-actions">
          <button class="btn-approve" data-action="approve" data-id="${event.id}">Approve</button>
          <button class="btn-reject" data-action="reject" data-id="${event.id}">Reject</button>
        </div>
      </article>
    `
    )
    .join("");

  container.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = parseInt(btn.dataset.id, 10);
      const adminKey = getAdminKey();
      try {
        if (btn.dataset.action === "approve") {
          await approveEvent(id, adminKey);
        } else {
          await rejectEvent(id, adminKey);
        }
        await loadPending(adminKey);
      } catch (err) {
        alert(err.message);
      }
    });
  });
}

async function loadPending(adminKey) {
  const errorEl = document.getElementById("admin-error");
  errorEl.hidden = true;

  try {
    const events = await fetchPendingEvents(adminKey);
    renderPending(events);
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
    document.getElementById("pending-list").innerHTML = "";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initNav();
  setActiveNav("admin");

  const keyInput = document.getElementById("admin-key");
  keyInput.value = getAdminKey();

  document.getElementById("load-pending").addEventListener("click", () => {
    const key = keyInput.value.trim();
    if (!key) {
      document.getElementById("admin-error").textContent = "Admin API key is required.";
      document.getElementById("admin-error").hidden = false;
      return;
    }
    saveAdminKey(key);
    loadPending(key);
  });

  if (getAdminKey()) {
    loadPending(getAdminKey());
  }
});
