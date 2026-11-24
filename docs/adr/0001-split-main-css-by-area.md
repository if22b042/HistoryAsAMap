# Split main.css into tokens, base, components and one file per area

`main.css` was one 1,932-line file with dark overrides scattered through it. We split it into `tokens.css`, `base.css`, `components.css`, `shell.css` and one file per area (`map`, `event`, `collections`, `game`, `admin`, plus the existing `tags.css`), loaded as plain `<link>` tags with no build step. Light and dark values live only in `tokens.css`. Reason: disjoint files let area slices be built in parallel and keep dark mode in one place. Cost: more requests; fine over HTTP/2 and revisit if first paint regresses.

## Considered options
- Re-skin `main.css` in place: cheapest, but blocks parallel work and leaves scattered dark overrides.
- Add a CSS build step (bundler): rejected, the project deliberately has no JS build.
