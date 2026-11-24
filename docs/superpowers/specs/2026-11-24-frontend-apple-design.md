# HAAM frontend redo: Apple-style design system

Date: 2026-11-24 · Branch: `redo/frontend-apple` (from `claude/curated-collections` 3926b48)

## Intent
Apply the design system shipped in CV Automatism (cool neutrals, system blue, pill controls, translucent sheets, light + dark) to all of HAAM's frontend, adapted to a map product. Why: one coherent, calm visual language that keeps the map as the hero.

## Depth (honest labels)
| Area | Depth |
| :-- | :-- |
| Map page chrome (filters, timeline, side/bottom sheet, basemap switcher) | RECOMPOSITION |
| Collections (6 templates) | RECOMPOSITION |
| Event, submit, preview, submitted, about, error, game, admin (7), base shell | RESTYLE (same layout) |

Nothing here is called a full redesign. Map tiles, the dark tile filter and the basemap/satellite exceptions are not restyled.

## Goals
- Every colour, font, radius, space and duration is a token in `:root`.
- Light + dark through `prefers-color-scheme` AND `:root[data-theme="dark"]`; `theme.js` keeps working unchanged in behaviour.
- Pill buttons, segmented controls, 36px controls with 44px hit area, 14/20px radii, tabular figures, sentence-case labels.
- Floating translucent sheets (blur; solid under `prefers-reduced-transparency`); hairline edges, layered elevation.
- Motion only `transform` and `opacity`, `cubic-bezier(.32,.72,0,1)`, press scale .97, full `prefers-reduced-motion` fallback.
- Map filters float on the Leaflet canvas; event details in a side sheet, bottom sheet on phones (draggable, pointer capture, velocity handoff, rubber-banding).
- Inter served locally from `haam/static/fonts/` (CSP `font-src 'self'` already allows it).

## Non-goals / anti-goals
- No CSP change, no new dependency, no JS build step.
- No changes to `models.py`, `migrations/`, `collections_service.py`, `auth.py`, `seed_demo.py`.
- No edits to existing tests. Every id, class, `data-*`, form field name, CSRF token and route stays.
- No invented metrics; no screenshots in the repo.
- Anti-goal: a pretty page that breaks map interaction, z-order against Leaflet panes (200-700), or contrast.

## Constraints found in recon
- `main.css` is 1,932 lines in 14+ sections; dark overrides are scattered (lines 587-592, 766, 1164-1166, 1429, 1700) and must fold into token overrides.
- z-index ladder 1..1300 plus `100000 !important` for selected markers; the navbar is 1100. New ladder goes into tokens (`--z-*`).
- CSP: `style-src 'unsafe-inline'` allowed, `script-src` has no inline; no inline scripts.
- JS builds markup in `map.js` (51 sites), `game.js` (19), `tag-picker.js` (14), `timeline.js` (13) and sets styles in `map.js` (13), `timeline.js` (7). JS style hooks stay; only class hooks change where listed in a slice brief.
- Tests assert markup in ~9 files (embed, collections_features, game, collection_editor, welcome...). Gate: `python -m pytest -q` (venv from the main checkout), `pyflakes haam`.
- Font Awesome 6.4.0 (SRI) stays for in-page content icons; shell icons become inline SVG with one stroke width (slice F).

## Approaches considered
1. **Re-skin in place** (rewrite `main.css` tokens only). Cheapest; leaves a 1.9k-line file and scattered dark overrides. Rejected: cannot parallelise.
2. **Split CSS by area, tokens first, then parallel slices** (chosen). Disjoint files per slice enable parallel worktrees; tokens give one place for light/dark.
3. **Port CV `styles.css` wholesale.** Fast but imports CV-only classes (`.drawer`, `.egrid`, CV preview fonts) and fights HAAM's class names. Rejected; we copy tokens and component patterns only.

## Architecture
```
css/tokens.css      :root tokens, dark blocks, @font-face, z-index ladder
css/base.css        reset, typography, focus, reduced-motion/transparency
css/components.css  buttons, seg, fields, chips, sheets, toasts, badges, figures
css/shell.css       navbar, footer, flashes (slice F)
css/map.css  event.css  collections.css  game.css  admin.css  tags.css
```
Load order in `base.html`: Font Awesome, tokens, base, components, shell, area files, tags. Old `main.css` is removed once empty. Old token names (`--surface`, `--text-muted`, ...) are kept as aliases of the new tokens during the transition so unsliced CSS keeps working, then removed in the last cleanup commit.

## Slices (disjoint file lists)
- A map page · B event/submit/preview/submitted/about/error + `_macros.html` · C collections · D game · E admin · F shell (`base.html`, nav, `theme.js`, footer, icons).
- Foundation (before slices): split, tokens, fonts, base/components, ADR + glossary.
- Merge order: F, B, E, D, C, A (smallest blast radius to biggest), full gate after each.

## Verification
pytest + pyflakes fresh; contrast script both themes (tints composited over real background; text 4.5:1, field borders and focus 3:1); browser pane at 1280 and 375, light and dark, console clean, no horizontal overflow, sheet drag/pan/pinch exercised; Hallmark `sloplint --before/--kept`; Impeccable audit + polish; review panel (CSS regression, a11y script, code review, independent Gemini verifier).

## Left to the builder
Exact component markup inside a slice, SVG icon drawing, specimen layout of `docs/ui-showcase.html`. Anything touching a risky area: stop and report.
