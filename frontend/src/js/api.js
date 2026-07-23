const API_BASE = import.meta.env.VITE_API_URL || "";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }

  return data;
}

export function fetchEvents(params = {}) {
  const query = new URLSearchParams();
  if (params.year_from != null) query.set("year_from", params.year_from);
  if (params.year_to != null) query.set("year_to", params.year_to);
  if (params.category) query.set("category", params.category);
  const qs = query.toString();
  return request(`/api/events${qs ? `?${qs}` : ""}`);
}

export function previewEvent(wikiLink) {
  return request("/api/events/preview", {
    method: "POST",
    body: JSON.stringify({ wiki_link: wikiLink }),
  });
}

export function createEvent(entry) {
  return request("/api/events", {
    method: "POST",
    body: JSON.stringify(entry),
  });
}

export function fetchPendingEvents(adminKey) {
  return request("/api/admin/events/pending", {
    headers: { "X-Admin-Key": adminKey },
  });
}

export function approveEvent(id, adminKey) {
  return request(`/api/admin/events/${id}/approve`, {
    method: "PATCH",
    headers: { "X-Admin-Key": adminKey },
  });
}

export function rejectEvent(id, adminKey) {
  return request(`/api/admin/events/${id}/reject`, {
    method: "PATCH",
    headers: { "X-Admin-Key": adminKey },
  });
}

export function fetchTags() {
  return request("/api/tags");
}
