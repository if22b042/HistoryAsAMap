# HAAM (History As A Map)

Flask app, tests with pytest, Alembic migrations, seed data in `seed/`. See README.md.

## Agent Workflow
Follows the user-level `agentize` skill (fixed principles live there; this section is configuration).

### Config
- Builder runner: opencode, run as: `opencode run -m <provider/model> -f .briefs/<task>.md "Do the task in the attached brief."`
- Briefs: `.briefs/<task>.md` (gitignored)
- Gate: `python -m pytest -q`
- Protected branch: main; working branch: `claude/<topic>`; push: not allowed unless asked; `gh`: check before use
- Risky areas (force NON_TRIVIAL/SIGNIFICANT): `haam/models.py`, `migrations/`, `haam/collections_service.py`, `haam/auth.py`, `seed_demo.py`
- Banned models: none declared; drop any model `opencode models` does not list
- Privacy: only public Wikipedia/Wikidata facts and coordinates go to outside models or search. Never send emails, `.env`, `instance/*.db` contents or edit/share tokens.
- Extras: frontend-chain yes · security-audit (user-invoked) yes · code graph none

### Model table (volatile, update when models change)
| Model | Family | Best for | Weak at | Context / cost |
| :-- | :-- | :-- | :-- | :-- |
| Sonnet 5.5 | Claude | planning, drafting data, multi-file code | cost vs. Haiku | mid |
| Haiku 5.5 | Claude | cheap fact checks, small patches | long reasoning | low |
| opencode/google models (e.g. google/gemini-3.6-flash) | Google | independent cross-check of facts | unverified for code | low |

Defaults: small patch -> Haiku; multi-file -> Sonnet 5.5; fact check -> Haiku plus one OpenCode (Google) model; verifier -> a different family than the builder.
