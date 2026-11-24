# HAAM frontend

The visual and interaction language of HistoryAsAMap's web UI: a quiet full-bleed map with floating controls.

## Language

**Token**:
A named CSS custom property in `:root` for a colour, font, radius, space, duration or layer. No stylesheet outside `tokens.css` holds a literal value for these.
_Avoid_: variable, theme value

**Material**:
A translucent, blurred surface (top bar, sheets, floating pills) that falls back to a solid fill when the user prefers reduced transparency.
_Avoid_: glass, frosted panel

**Sheet**:
A floating panel over the map that holds details or filters: a side sheet on wide screens, a draggable bottom sheet on phones.
_Avoid_: drawer, sidebar, modal (a modal blocks the page; a sheet does not)

**Segmented control**:
A pill-shaped group of mutually exclusive options with one raised active thumb.
_Avoid_: tabs, toggle group

**Scrubber**:
The year slider and timeline control that moves the map through time.
_Avoid_: range bar, noUiSlider (the library behind it)

**Figures strip**:
A row of large tabular numbers with small labels that shows counts (events, collections, entries).
_Avoid_: stats bar, KPI row

**Tint**:
A token-derived translucent colour used for clusters, the heat layer and status pills, always checked after compositing over its real background.
_Avoid_: overlay colour

**Basemap exception**:
The map tiles, their dark-mode filter, the basemap switcher and the satellite/plain views, which are not restyled to match the theme.
_Avoid_: map theme
