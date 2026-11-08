// The map's event data: compact column chunks (see haam/feed.py), decoded into
// one plain object per event. Chunk URLs are versioned, so the browser keeps them
// and a repeat visit downloads nothing.

const WIKI_PREFIX = "https://en.wikipedia.org/wiki/";

export function formatYear(year) {
  if (year === null || year === undefined) return "";
  if (year < 0) return `${-year} BC`;
  if (year < 1000) return `AD ${year}`;
  return String(year);
}

export async function getJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

/** The same URL a second time if the first try fails (a flaky mobile connection). */
export function getJsonRetry(url, tries = 2) {
  return getJson(url).catch((error) => {
    if (tries <= 1) throw error;
    return new Promise((resolve) => setTimeout(resolve, 800)).then(() => getJsonRetry(url, tries - 1));
  });
}

function wikiUrl(field, title) {
  if (field === "") return WIKI_PREFIX + title.replaceAll(" ", "_");
  return /^https?:\/\//.test(field) ? field : WIKI_PREFIX + field;
}

/** A core chunk → event objects (the shape the map has always used; excerpts come later). */
export function decodeCore(chunk) {
  const events = new Array(chunk.count);
  for (let i = 0; i < chunk.count; i += 1) {
    const year = chunk.year[i];
    const displayYear = formatYear(year);
    events[i] = {
      id: chunk.id[i],
      title: chunk.title[i],
      year,
      display_year: displayYear,
      date: chunk.date[i] || displayYear,
      excerpt: "",
      wiki_url: wikiUrl(chunk.wiki[i], chunk.title[i]),
      lat: chunk.lat[i],
      lon: chunk.lon[i],
      category: chunk.categories[chunk.cat[i]],
      tags: chunk.tags[i],
    };
  }
  return events;
}

/** The chunk an event id belongs to (ids are spread over the chunks by id % modulus). */
export function chunkOf(manifest, id) {
  const residue = id % manifest.modulus;
  for (let i = 0; i < manifest.bounds.length - 1; i += 1) {
    if (residue >= manifest.bounds[i] && residue < manifest.bounds[i + 1]) return i;
  }
  return 0;
}

/** Chunk numbers in loading order: the one holding ``firstId`` (e.g. ?event=) first. */
export function chunkOrder(manifest, firstId) {
  const order = manifest.core.map((_, i) => i);
  if (firstId) {
    const first = chunkOf(manifest, firstId);
    order.splice(order.indexOf(first), 1);
    order.unshift(first);
  }
  return order;
}

/** Events sorted by year, then title (how the server sorts each chunk). */
export function compareEvents(a, b) {
  if (a.year !== b.year) return a.year - b.year;
  if (a.title !== b.title) return a.title < b.title ? -1 : 1;
  return a.id - b.id;
}

/** Merge two lists that are each sorted with compareEvents. */
export function mergeSorted(a, b) {
  const out = new Array(a.length + b.length);
  let i = 0;
  let j = 0;
  let k = 0;
  while (i < a.length && j < b.length) out[k++] = compareEvents(a[i], b[j]) <= 0 ? a[i++] : b[j++];
  while (i < a.length) out[k++] = a[i++];
  while (j < b.length) out[k++] = b[j++];
  return out;
}

export async function loadManifest() {
  return getJson("/api/events/manifest");
}

/** Every approved event, all chunks at once (for pages that just need the list). */
export async function loadAllEvents(manifest) {
  const chunks = await Promise.all(manifest.core.map((url) => getJsonRetry(url)));
  return chunks.map(decodeCore).reduce(mergeSorted, []);
}
