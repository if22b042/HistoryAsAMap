// Game page: five events, the player pins where each happened.
// Daily mode: the same five for everyone each day; progress and the streak live in
// localStorage, so a reload keeps the game. Practice mode (?mode=practice): random
// sets of five, optionally from one era or category; nothing is stored.
/* global L */

const STORAGE_KEY = "haam-game-v1";
const ROOT = document.getElementById("game");
const $ = (id) => document.getElementById(id);

const CATEGORY_LABELS = {
  military: "Military",
  diplomatic: "Diplomatic",
  naval: "Naval",
  scientific: "Scientific",
  natural: "Natural",
  other: "Other",
};

// ---------------------------------------------------------------- storage

function loadStore() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (parsed && typeof parsed === "object" && parsed.days) return parsed;
  } catch (e) { /* storage blocked or corrupt */ }
  return { days: {}, streak: { current: 0, best: 0, last: null } };
}

function saveStore(store) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch (e) { /* storage blocked or full: the game still works without it */ }
}

// ---------------------------------------------------------------- helpers

function formatKm(km) {
  if (km < 1) return "less than 1 km";
  return `${Math.round(km).toLocaleString("en")} km`;
}

const formatPoints = (n) => n.toLocaleString("en");

function emojiFor(points, max) {
  const share = points / max;
  if (share >= 0.8) return "🟩";
  if (share >= 0.5) return "🟨";
  if (share >= 0.2) return "🟧";
  return "🟥";
}

function addDays(iso, days) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d + days));
  return date.toISOString().slice(0, 10);
}

function formatDay(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
    day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
  });
}

function safeWikipediaUrl(url) {
  return /^https:\/\/en\.wikipedia\.org\/wiki\//.test(url || "") ? url : null;
}

function safeLocalUrl(url) {
  return /^\/(?!\/)/.test(url || "") ? url : null;
}

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function dayUrl(day) {
  return `${ROOT.dataset.pageUrl}?date=${encodeURIComponent(day)}`;
}

// ---------------------------------------------------------------- state

const PRACTICE = new URLSearchParams(window.location.search).get("mode") === "practice";
const store = loadStore();
let puzzle = null;
let record = null; // this day's progress: { rounds, guesses }
let showingResult = false; // the last guess is revealed, waiting for "Next"
let pin = null; // [lat, lng] the player picked for the current round

// ---------------------------------------------------------------- map

const map = L.map("game-map", { worldCopyJump: true, minZoom: 2 }).setView([30, 10], 2);

// Esri's gray canvas base maps without their label layer, so zooming in does not
// reveal the answer. (CARTO's no-label tiles now need an API key.)
const tileUrl = () => {
  const style = document.documentElement.dataset.theme === "dark" ? "World_Dark_Gray_Base" : "World_Light_Gray_Base";
  return `https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/${style}/MapServer/tile/{z}/{y}/{x}`;
};
const tiles = L.tileLayer(tileUrl(), {
  maxZoom: 16,
  attribution: "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors, and the GIS user community",
}).addTo(map);

// Follow the theme toggle; the pin line takes the theme's text colour too.
new MutationObserver(() => {
  tiles.setUrl(tileUrl());
  layer.eachLayer((item) => {
    if (item instanceof L.Polyline && !(item instanceof L.CircleMarker)) item.setStyle(lineStyle());
  });
}).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

const layer = L.layerGroup().addTo(map);
let guessMarker = null;

function guessStyle() {
  return { radius: 9, weight: 3, color: "#fff", fillColor: cssVar("--accent", "#3182ce"), fillOpacity: 1 };
}

function answerStyle() {
  return { radius: 9, weight: 3, color: "#fff", fillColor: cssVar("--cat-military", "#e53e3e"), fillOpacity: 1 };
}

function lineStyle() {
  return { color: cssVar("--text-strong", "#1a202c"), weight: 3, opacity: 0.85, dashArray: "8 6" };
}

function drawResult(guess, focus) {
  const from = [guess.lat, guess.lon];
  // Draw the answer on the copy of the world nearest the guess, so the line is short.
  let lon = guess.answer.lon;
  while (lon - guess.lon > 180) lon -= 360;
  while (guess.lon - lon > 180) lon += 360;
  const to = [guess.answer.lat, lon];
  L.circleMarker(from, guessStyle()).bindTooltip("Your guess").addTo(layer);
  L.circleMarker(to, answerStyle()).bindTooltip(guess.answer.title).addTo(layer);
  L.polyline([from, to], lineStyle()).addTo(layer);
  if (focus) map.fitBounds(L.latLngBounds([from, to]), { padding: [40, 40], maxZoom: 7 });
}

map.on("click", (e) => {
  if (!record || showingResult || record.guesses.length >= record.rounds.length) return;
  pin = [e.latlng.lat, e.latlng.lng];
  if (guessMarker) guessMarker.setLatLng(e.latlng);
  else guessMarker = L.circleMarker(e.latlng, guessStyle()).addTo(layer);
  $("guess-btn").disabled = false;
  $("guess-btn-map").hidden = false;
  $("round-hint").textContent = "Click again to move your pin.";
});

// ---------------------------------------------------------------- rendering

function renderProgress() {
  const list = $("game-progress");
  list.replaceChildren();
  record.rounds.forEach((round, i) => {
    const guess = record.guesses[i];
    const item = el("li", "game-step");
    if (guess) {
      item.classList.add("done");
      item.textContent = emojiFor(guess.points, puzzle.max_points);
      item.title = `${round.title}: ${formatPoints(guess.points)} points`;
    } else {
      item.textContent = String(i + 1);
      if (i === record.guesses.length) item.classList.add("current");
    }
    list.append(item);
  });
}

function renderRound() {
  const index = showingResult ? record.guesses.length - 1 : record.guesses.length;
  const round = record.rounds[index];
  $("game-round").hidden = false;
  $("game-summary").hidden = true;
  $("round-num").textContent = `Event ${index + 1} of ${record.rounds.length}`;
  $("round-title").textContent = round.title;
  $("round-date").textContent = round.date;
  const category = $("round-category");
  category.firstElementChild.className = `dot dot-${round.category}`;
  category.lastElementChild.textContent = CATEGORY_LABELS[round.category] || round.category;
  $("round-excerpt").textContent = round.excerpt;
  $("round-excerpt").hidden = !round.excerpt;

  $("round-guess").hidden = showingResult;
  $("guess-btn-map").hidden = showingResult || !pin;
  $("round-result").hidden = !showingResult;
  if (!showingResult) {
    $("guess-btn").disabled = !pin;
    $("round-hint").textContent = pin
      ? "Click again to move your pin."
      : "Click the map to place your pin, then confirm.";
    return;
  }
  const guess = record.guesses[index];
  $("result-points").textContent = formatPoints(guess.points);
  $("result-distance").textContent = `Your pin was ${formatKm(guess.km)} away.`;
  $("result-answer").textContent = guess.answer.country
    ? `${guess.answer.title} took place in ${guess.answer.country}.`
    : `The red dot marks where ${guess.answer.title} took place.`;
  const wiki = safeWikipediaUrl(guess.answer.wiki_url);
  $("result-wiki").hidden = !wiki;
  if (wiki) $("result-wiki").href = wiki;
  const onMap = safeLocalUrl(guess.answer.map_url);
  $("result-map").hidden = !onMap;
  if (onMap) $("result-map").href = onMap;
  const last = record.guesses.length >= record.rounds.length;
  $("next-btn").textContent = last ? "See your score" : "Next event";
  $("next-btn").focus({ preventScroll: true });
}

function total() {
  return record.guesses.reduce((sum, g) => sum + g.points, 0);
}

function shareText() {
  const max = puzzle.max_points * record.rounds.length;
  const squares = record.guesses.map((g) => emojiFor(g.points, puzzle.max_points)).join("");
  const url = new URL(dayUrl(puzzle.date), window.location.origin).href;
  return [
    `History As A Map · Game #${puzzle.number}`,
    `${squares} ${formatPoints(total())} / ${formatPoints(max)}`,
    url,
  ].join("\n");
}

let countdownTimer = null;

function renderCountdown() {
  const target = new Date(puzzle.next_game_at).getTime();
  const tick = () => {
    const left = Math.max(0, target - Date.now());
    if (left === 0) {
      clearInterval(countdownTimer);
      const link = el("a", null, "A new game is ready – play it");
      link.href = ROOT.dataset.pageUrl;
      $("summary-countdown").replaceChildren(link);
      return;
    }
    const s = Math.floor(left / 1000);
    const hms = [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60]
      .map((n) => String(n).padStart(2, "0")).join(":");
    $("summary-countdown").textContent = `Next game in ${hms} (midnight UTC).`;
  };
  clearInterval(countdownTimer);
  tick();
  countdownTimer = setInterval(tick, 1000);
}

function currentStreak() {
  const { current, last } = store.streak;
  // A streak survives until the day after its last game ends.
  return last === puzzle.today || last === addDays(puzzle.today, -1) ? current : 0;
}

function renderSummary() {
  $("game-round").hidden = true;
  $("game-summary").hidden = false;
  $("guess-btn-map").hidden = true;
  $("summary-total").textContent = formatPoints(total());
  $("summary-max").textContent = `/ ${formatPoints(puzzle.max_points * record.rounds.length)}`;

  const list = $("summary-list");
  list.replaceChildren();
  record.rounds.forEach((round, i) => {
    const guess = record.guesses[i];
    const item = el("li");
    item.append(
      el("span", "game-summary-emoji", emojiFor(guess.points, puzzle.max_points)),
      el("span", "game-summary-title", round.title),
      el("span", "game-summary-points", `${formatPoints(guess.points)} · ${formatKm(guess.km)}`),
    );
    list.append(item);
  });

  $("summary-daily").hidden = PRACTICE;
  $("practice-again").hidden = !PRACTICE;
  if (PRACTICE) {
    $("practice-again").focus({ preventScroll: true });
    return;
  }
  $("share-text").value = shareText();
  const streak = currentStreak();
  $("summary-streak").textContent = `Streak: ${streak} ${streak === 1 ? "day" : "days"}`
    + ` · best ${store.streak.best}`;
  renderCountdown();
}

function render() {
  renderProgress();
  const finished = record.guesses.length >= record.rounds.length;
  if (finished && !showingResult) renderSummary();
  else renderRound();
}

function showAllResults() {
  layer.clearLayers();
  guessMarker = null;
  record.guesses.forEach((g) => drawResult(g, false));
  const points = record.guesses.flatMap((g) => [[g.lat, g.lon], [g.answer.lat, g.answer.lon]]);
  if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [30, 30], maxZoom: 5 });
}

// ---------------------------------------------------------------- actions

function finishDay() {
  if (PRACTICE || !puzzle.is_today) return;
  const { streak } = store;
  if (streak.last === puzzle.date) return;
  streak.current = streak.last === addDays(puzzle.date, -1) ? streak.current + 1 : 1;
  streak.best = Math.max(streak.best || 0, streak.current);
  streak.last = puzzle.date;
}

async function submitGuess() {
  if (!pin) return;
  const button = $("guess-btn");
  button.disabled = true;
  $("guess-btn-map").hidden = true;
  $("game-message").textContent = "";
  try {
    const guessed = { index: record.guesses.length, lat: pin[0], lon: pin[1] };
    const body = PRACTICE
      ? { ...guessed, seed: puzzle.seed, era: puzzle.era, category: puzzle.category }
      : { ...guessed, date: puzzle.date };
    const response = await fetch(PRACTICE ? ROOT.dataset.practiceCheckUrl : ROOT.dataset.checkUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    const guess = { lat: pin[0], lon: pin[1], km: result.km, points: result.points, answer: result.answer };
    record.guesses.push(guess);
    if (record.guesses.length >= record.rounds.length) finishDay();
    if (!PRACTICE) saveStore(store);
    if (guessMarker) {
      layer.removeLayer(guessMarker);
      guessMarker = null;
    }
    pin = null;
    showingResult = true;
    drawResult(guess, true);
    render();
    if (window.matchMedia("(max-width: 768px)").matches) {
      $("round-result").scrollIntoView({ block: "center" });
    }
  } catch (e) {
    button.disabled = false;
    $("guess-btn-map").hidden = false;
    $("game-message").textContent = "Could not check your guess. Please try again.";
  }
}

function nextRound() {
  showingResult = false;
  if (record.guesses.length >= record.rounds.length) {
    showAllResults();
  } else {
    layer.clearLayers();
    map.setView([30, 10], 2);
  }
  render();
}

$("guess-btn").addEventListener("click", submitGuess);
$("guess-btn-map").addEventListener("click", submitGuess);
$("next-btn").addEventListener("click", nextRound);

// ---------------------------------------------------------------- start

function sameRounds(a, b) {
  return Array.isArray(a) && a.length === b.length && a.every((r, i) => r.title === b[i].title);
}

function renderHeader() {
  const label = puzzle.is_today ? "Today" : formatDay(puzzle.date);
  $("game-meta").textContent = `Game #${puzzle.number} · ${label}`
    + (puzzle.is_today ? ` · ${formatDay(puzzle.date)}` : "");
  $("game-archive-note").hidden = puzzle.is_today;
  const links = [["day-prev", puzzle.previous], ["day-next", puzzle.next]];
  for (const [id, day] of links) {
    $(id).hidden = !day;
    if (day) $(id).href = day === puzzle.today ? ROOT.dataset.pageUrl : dayUrl(day);
  }
  $("day-today").hidden = puzzle.is_today;
}

function renderModes() {
  $("mode-daily").classList.toggle("active", !PRACTICE);
  $("mode-practice").classList.toggle("active", PRACTICE);
  $(PRACTICE ? "mode-practice" : "mode-daily").setAttribute("aria-current", "page");
  $("practice-filters").hidden = !PRACTICE;
}

function resetBoard() {
  showingResult = false;
  pin = null;
  guessMarker = null;
  layer.clearLayers();
  map.setView([30, 10], 2);
}

async function loadPractice() {
  const params = new URLSearchParams();
  if ($("practice-era").value) params.set("era", $("practice-era").value);
  if ($("practice-category").value) params.set("category", $("practice-category").value);
  $("game-message").textContent = "";
  $("game-meta").textContent = "Loading a practice set…";
  try {
    const query = params.toString();
    const response = await fetch(ROOT.dataset.practiceUrl + (query ? `?${query}` : ""));
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    puzzle = await response.json();
  } catch (e) {
    $("game-meta").textContent = "The practice set could not be loaded. Please try again.";
    return;
  }
  $("game-meta").textContent = "Practice · random events, not counted for your streak";
  resetBoard();
  if (!puzzle.rounds.length) {
    record = null;
    $("game-progress").replaceChildren();
    $("game-round").hidden = true;
    $("game-summary").hidden = true;
    $("guess-btn-map").hidden = true;
    $("game-message").textContent = "No events match these filters. Try another era or category.";
    return;
  }
  record = { rounds: puzzle.rounds, guesses: [] };
  render();
}

$("practice-filters").addEventListener("submit", (e) => {
  e.preventDefault();
  loadPractice();
});
$("practice-era").addEventListener("change", loadPractice);
$("practice-category").addEventListener("change", loadPractice);
$("practice-again").addEventListener("click", loadPractice);

async function init() {
  renderModes();
  if (PRACTICE) {
    await loadPractice();
    return;
  }
  const requested = new URLSearchParams(window.location.search).get("date");
  const day = requested && /^\d{4}-\d{2}-\d{2}$/.test(requested) ? requested : "today";
  try {
    const response = await fetch(ROOT.dataset.puzzleUrl.replace("DAY", day));
    if (response.status === 404) {
      $("game-meta").textContent = "There is no game for that day.";
      const link = el("a", null, "Play today's game");
      link.href = ROOT.dataset.pageUrl;
      $("game-message").replaceChildren(link);
      return;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    puzzle = await response.json();
  } catch (e) {
    $("game-meta").textContent = "The game could not be loaded. Please reload the page.";
    return;
  }

  renderHeader();
  if (!puzzle.rounds.length) {
    $("game-message").textContent = "There are no events to play yet.";
    return;
  }

  const saved = store.days[puzzle.date];
  // Keep saved progress unless the day's events changed since it was played.
  if (saved && sameRounds(saved.rounds, puzzle.rounds) && Array.isArray(saved.guesses)) {
    record = saved;
  } else {
    record = { rounds: puzzle.rounds, guesses: [] };
    store.days[puzzle.date] = record;
  }
  if (record.guesses.length >= record.rounds.length) showAllResults();
  render();
}

init();
