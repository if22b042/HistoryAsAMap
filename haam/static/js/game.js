// Game page: five events, the player pins where each happened.
// Daily mode: the same five for everyone each day; progress and the streak live in
// localStorage, so a reload keeps the game. Practice mode (?mode=practice): random
// sets of five, optionally from one era or category; nothing is stored.
// Hard mode (&hard=1, either mode): the year is hidden and guessed too; the daily
// hard game keeps its own progress and streak.
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
    if (parsed && typeof parsed === "object" && parsed.days) {
      parsed.streak = parsed.streak || { current: 0, best: 0, last: null };
      parsed.hardStreak = parsed.hardStreak || { current: 0, best: 0, last: null };
      return parsed;
    }
  } catch (e) { /* storage blocked or corrupt */ }
  return {
    days: {},
    streak: { current: 0, best: 0, last: null },
    hardStreak: { current: 0, best: 0, last: null },
  };
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

const PARAMS = new URLSearchParams(window.location.search);
const PRACTICE = PARAMS.get("mode") === "practice";
const HARD = PARAMS.get("hard") === "1";

/** The game page URL for a mode, day and difficulty. */
function pageUrl({ practice = PRACTICE, hard = HARD, day = null } = {}) {
  const params = new URLSearchParams();
  if (practice) params.set("mode", "practice");
  if (day && !practice) params.set("date", day);
  if (hard) params.set("hard", "1");
  const query = params.toString();
  return ROOT.dataset.pageUrl + (query ? `?${query}` : "");
}

const dayUrl = (day) => pageUrl({ day });

// ---------------------------------------------------------------- years

function formatYear(year) {
  if (year === null || year === undefined) return "";
  if (year < 0) return `${-year} BC`;
  if (year < 1000) return `AD ${year}`;
  return String(year);
}

/** "1066", "-44", "44 BC", "AD 9", "9 CE" → a year (negative = BC), else null. */
function parseYear(text) {
  const m = /^\s*(?:(AD|CE)\s*)?(-)?(\d{1,5})\s*(BCE|BC|AD|CE)?\s*$/i.exec(text || "");
  if (!m || (m[2] && (m[1] || m[4]))) return null;
  let year = Number(m[3]);
  if (m[2] || /^BC/i.test(m[4] || "")) year = -year;
  if (year === 0 || year < SLIDER_FROM || year > CURRENT_YEAR) return null;
  return year;
}

// The slider is not linear: recent centuries get more room than antiquity.
const CURRENT_YEAR = new Date().getUTCFullYear();
const SLIDER_FROM = -3000;
const SLIDER_MAX = 1000;
const SLIDER_SPAN = CURRENT_YEAR - SLIDER_FROM;

function sliderToYear(value) {
  const t = 1 - value / SLIDER_MAX;
  const year = Math.round(CURRENT_YEAR - SLIDER_SPAN * t * t);
  return year === 0 ? 1 : year;
}

function yearToSlider(year) {
  const t = Math.sqrt(Math.max(0, Math.min(1, (CURRENT_YEAR - year) / SLIDER_SPAN)));
  return Math.round((1 - t) * SLIDER_MAX);
}

function plural(n, word) {
  return `${n.toLocaleString("en")} ${word}${n === 1 ? "" : "s"}`;
}

// ---------------------------------------------------------------- state

const store = loadStore();
let puzzle = null;
let record = null; // this day's progress: { rounds, guesses }
let showingResult = false; // the last guess is revealed, waiting for "Next"
let pin = null; // [lat, lng] the player picked for the current round
let yearGuess = null; // hard mode: the year the player picked for the current round

const streakOf = () => (HARD ? store.hardStreak : store.streak);
const storeKey = (day) => (HARD ? `${day}:hard` : day);
const canConfirm = () => Boolean(pin) && (!HARD || yearGuess !== null);

function updateConfirm() {
  const ready = canConfirm();
  $("guess-btn").disabled = !ready;
  $("guess-btn-map").hidden = !ready || showingResult;
  let hint;
  if (!HARD) hint = pin ? "Click again to move your pin." : "Click the map to place your pin, then confirm.";
  else if (!pin && yearGuess === null) hint = "Click the map to place your pin and pick a year.";
  else if (!pin) hint = "Now click the map to place your pin.";
  else if (yearGuess === null) hint = "Now pick a year: type it or use the slider.";
  else hint = "Click again to move your pin, or change the year.";
  $("round-hint").textContent = hint;
}

function setYear(year, { fromSlider = false, fromInput = false } = {}) {
  yearGuess = year;
  $("year-shown").textContent = year === null ? "" : formatYear(year);
  if (year !== null && !fromSlider) $("year-slider").value = yearToSlider(year);
  if (year !== null && !fromInput) $("year-input").value = formatYear(year);
  $("year-input").classList.toggle("year-input-invalid", fromInput && year === null && $("year-input").value.trim() !== "");
  updateConfirm();
}

function resetYear() {
  yearGuess = null;
  $("year-input").value = "";
  $("year-slider").value = yearToSlider(1500);
  $("year-shown").textContent = "";
  $("year-input").classList.remove("year-input-invalid");
}

$("year-input").addEventListener("input", () => setYear(parseYear($("year-input").value), { fromInput: true }));
$("year-slider").addEventListener("input", () => setYear(sliderToYear(Number($("year-slider").value)), { fromSlider: true }));

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
  updateConfirm();
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
  // In hard mode the result shows the real title (the clue's has its year hidden).
  const revealed = showingResult ? record.guesses[index].answer : null;
  $("round-title").textContent = HARD && revealed ? revealed.title : round.title;
  $("round-date").textContent = round.date || (revealed ? revealed.date : "Year hidden");
  const category = $("round-category");
  category.firstElementChild.className = `dot dot-${round.category}`;
  category.lastElementChild.textContent = CATEGORY_LABELS[round.category] || round.category;
  $("round-excerpt").textContent = round.excerpt;
  $("round-excerpt").hidden = !round.excerpt;

  $("round-guess").hidden = showingResult;
  $("round-year").hidden = !HARD;
  $("round-result").hidden = !showingResult;
  if (!showingResult) {
    updateConfirm();
    return;
  }
  $("guess-btn-map").hidden = true;
  const guess = record.guesses[index];
  $("result-points").textContent = formatPoints(guess.points);
  $("result-distance").textContent = `Your pin was ${formatKm(guess.km)} away.`;
  $("result-breakdown").hidden = !HARD;
  $("result-year").hidden = !HARD;
  if (HARD) {
    $("result-breakdown").textContent = `${formatPoints(guess.locationPoints)} for the place`
      + ` + ${formatPoints(guess.yearPoints)} for the year`;
    $("result-year").textContent = guess.yearError === 0
      ? `Your year ${formatYear(guess.year)} was exactly right.`
      : `Your year ${formatYear(guess.year)} was ${plural(guess.yearError, "year")} off: `
        + `it was ${guess.answer.date}.`;
  }
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
    `History As A Map · Game #${puzzle.number}${HARD ? " (Hard)" : ""}`,
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
      link.href = pageUrl({ practice: false });
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
  const { current, last } = streakOf();
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
      el("span", "game-summary-title", HARD ? guess.answer.title : round.title),
      el("span", "game-summary-points", `${formatPoints(guess.points)} · ${formatKm(guess.km)}`
        + (HARD ? ` · ${guess.yearError === 0 ? "exact year" : `${plural(guess.yearError, "year")} off`}` : "")),
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
  $("summary-streak").textContent = `${HARD ? "Hard streak" : "Streak"}: ${streak} ${streak === 1 ? "day" : "days"}`
    + ` · best ${streakOf().best}`;
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
  const streak = streakOf();
  if (streak.last === puzzle.date) return;
  streak.current = streak.last === addDays(puzzle.date, -1) ? streak.current + 1 : 1;
  streak.best = Math.max(streak.best || 0, streak.current);
  streak.last = puzzle.date;
}

async function submitGuess() {
  if (!canConfirm()) return;
  const button = $("guess-btn");
  button.disabled = true;
  $("guess-btn-map").hidden = true;
  $("game-message").textContent = "";
  try {
    const guessed = { index: record.guesses.length, lat: pin[0], lon: pin[1] };
    if (HARD) Object.assign(guessed, { hard: true, year: yearGuess });
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
    if (HARD) {
      Object.assign(guess, {
        year: yearGuess,
        yearError: result.year_error,
        yearPoints: result.year_points,
        locationPoints: result.location_points,
      });
    }
    record.guesses.push(guess);
    if (record.guesses.length >= record.rounds.length) finishDay();
    if (!PRACTICE) saveStore(store);
    if (guessMarker) {
      layer.removeLayer(guessMarker);
      guessMarker = null;
    }
    pin = null;
    resetYear();
    showingResult = true;
    drawResult(guess, true);
    render();
    if (window.matchMedia("(max-width: 768px)").matches) {
      $("round-result").scrollIntoView({ block: "center" });
    }
  } catch (e) {
    updateConfirm();
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
  $("game-meta").textContent = `Game #${puzzle.number}${HARD ? " · Hard" : ""} · ${label}`
    + (puzzle.is_today ? ` · ${formatDay(puzzle.date)}` : "");
  $("game-archive-note").hidden = puzzle.is_today;
  const links = [["day-prev", puzzle.previous], ["day-next", puzzle.next]];
  for (const [id, day] of links) {
    $(id).hidden = !day;
    if (day) $(id).href = day === puzzle.today ? pageUrl({ practice: false }) : dayUrl(day);
  }
  $("day-today").hidden = puzzle.is_today;
}

function renderModes() {
  $("mode-daily").classList.toggle("active", !PRACTICE);
  $("mode-practice").classList.toggle("active", PRACTICE);
  $(PRACTICE ? "mode-practice" : "mode-daily").setAttribute("aria-current", "page");
  $("mode-daily").href = pageUrl({ practice: false });
  $("mode-practice").href = pageUrl({ practice: true });
  $("day-today").href = pageUrl({ practice: false });
  $("practice-filters").hidden = !PRACTICE;
  $("hard-toggle").checked = HARD;
}

// Switching difficulty reloads the page: the clues differ (years hidden or not).
$("hard-toggle").addEventListener("change", () => {
  const day = PRACTICE || !puzzle || puzzle.is_today ? null : puzzle.date;
  window.location.href = pageUrl({ hard: $("hard-toggle").checked, day });
});

function resetBoard() {
  showingResult = false;
  pin = null;
  resetYear();
  guessMarker = null;
  layer.clearLayers();
  map.setView([30, 10], 2);
}

async function loadPractice() {
  const params = new URLSearchParams();
  if ($("practice-era").value) params.set("era", $("practice-era").value);
  if ($("practice-category").value) params.set("category", $("practice-category").value);
  if (HARD) params.set("hard", "1");
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
  $("game-meta").textContent = `Practice${HARD ? " · Hard" : ""} · random events, not counted for your streak`;
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
    const response = await fetch(ROOT.dataset.puzzleUrl.replace("DAY", day) + (HARD ? "?hard=1" : ""));
    if (response.status === 404) {
      $("game-meta").textContent = "There is no game for that day.";
      const link = el("a", null, "Play today's game");
      link.href = pageUrl({ practice: false });
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

  const saved = store.days[storeKey(puzzle.date)];
  // Keep saved progress unless the day's events changed since it was played.
  if (saved && sameRounds(saved.rounds, puzzle.rounds) && Array.isArray(saved.guesses)) {
    record = saved;
  } else {
    record = { rounds: puzzle.rounds, guesses: [] };
    store.days[storeKey(puzzle.date)] = record;
  }
  if (record.guesses.length >= record.rounds.length) showAllResults();
  render();
}

init();
