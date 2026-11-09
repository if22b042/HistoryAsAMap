"""Excerpt limit vs. search RELEVANCE for ten named people.

For each term, every event whose full text (title + date + summary) contains
the word is labelled by a regex describing the intended person:

    right  the word refers to the person (Duke of Wellington, George Washington)
    wrong  same word, another meaning (Wellington NZ, Washington state, Alexander Suvorov)

For each excerpt limit N we then count what the search shows:

    right shown / right missed   (recall of the real person)
    wrong shown / wrong missed   (noise the search would add)
    precision = right shown / everything shown

The labels are regexes, not human judgement: spot-check with --show-wrong.

    python analysis/relevance_eval.py --db ../old/instance/haam.db
    python analysis/relevance_eval.py --show-wrong washington
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from excerpt_length_eval import DEFAULT_DB, excerpt  # noqa: E402

LIMITS = [100, 140, 200, 400, 600]

# term -> regex that identifies the intended person in the surrounding text.
# None = every occurrence counts as the person.
TERMS = {
    "napoleon": r"Napoleon(?! III| II\b|,? Ohio)",
    "caesar": r"Julius Caesar|Gaius Julius|Caesar(?:'s|’s)|\bCaesar\b",
    "alexander": r"Alexander the Great|Alexander III of Macedon|Alexander of Macedon",
    "wellington": r"Duke of Wellington|(?:Marquess|Marquis|Earl|Viscount|Lord|General) (?:of )?Wellington|Arthur Wellesley|Wellington(?:'s|’s) (?:army|forces|troops|men|retreat|Anglo)",
    "nelson": r"Horatio Nelson|(?:Lord|Admiral|Commodore|Captain|Rear-Admiral|Vice-Admiral|Sir) (?:Horatio )?Nelson",
    "washington": r"George Washington|General Washington|Gen\. Washington|President Washington(?! Lu)|Washington(?:'s|’s) (?:army|forces|troops|men|Continental)",
    "scipio": None,
    "saladin": None,
    "genghis": None,
    "cromwell": r"Oliver Cromwell|Richard Cromwell|Henry Cromwell|Cromwellian|Lord Protector",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--limits", type=int, nargs="+", default=LIMITS)
    ap.add_argument("--show-wrong", metavar="TERM", help="list events labelled wrong (or right, with --show-right) for one term")
    ap.add_argument("--show-right", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rows = con.execute("select title, date_label, year, summary from haam_events where status='approved'").fetchall()
    con.close()

    print(f"{len(rows)} approved events; limits {args.limits}\n")
    print(f"{'term':<11}{'right':>6}{'wrong':>6} | " + " | ".join(f"{n:>4}: R found/miss  W found/miss  prec" for n in args.limits))
    for term, sense in TERMS.items():
        word = re.compile(rf"\b{term}\b", re.I)
        sense_re = re.compile(sense, re.I) if sense else None
        events = []
        for title, date, year, summary in rows:
            full = f"{title} {date} {year} {summary or ''}"
            if not word.search(full):
                continue
            label = "right" if (sense_re is None or sense_re.search(full)) else "wrong"
            events.append((title, summary, date, year, label))
        if args.show_wrong == term:
            want = "right" if args.show_right else "wrong"
            for title, summary, *_rest, label in events:
                if label == want:
                    m = word.search(f"{title} {summary or ''}")
                    t = f"{title} {summary or ''}"
                    print(f"  {title} | ...{t[max(0, m.start() - 40):m.end() + 40]!r}")
            continue
        right = sum(1 for e in events if e[4] == "right")
        wrong = len(events) - right
        cells = []
        for n in args.limits:
            rf = rm = wf = wm = 0
            for title, summary, date, year, label in events:
                seen = bool(word.search(f"{title} {date} {year} {excerpt(summary, n)}"))
                if label == "right":
                    rf, rm = rf + seen, rm + (not seen)
                else:
                    wf, wm = wf + seen, wm + (not seen)
            prec = rf / (rf + wf) if rf + wf else 1.0
            cells.append(f"{n:>4}: {rf:>4}/{rm:<4}   {wf:>4}/{wm:<4}   {prec:>4.0%}")
        print(f"{term:<11}{right:>6}{wrong:>6} | " + " | ".join(cells))


if __name__ == "__main__":
    main()
