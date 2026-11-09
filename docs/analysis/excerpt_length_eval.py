"""How much does the excerpt length limit hurt the map's client-side search?

The map searches title + excerpt (first N characters of the summary) + date.
Ground truth is "the word occurs in the title, the date or the FULL summary".
For every query term and every limit N we count, over all (term, event) pairs:

    TP  search finds it and it is in the full text
    FN  in the full text, but the search misses it (the Zama/Hannibal case)
    FP  search finds it but it is not in the full text (impossible: the excerpt
        is a prefix, so always 0; kept so the matrix is complete)
    TN  neither

Read-only: opens the DB in read-only mode. Standard library only.

    python analysis/excerpt_length_eval.py --db ../old/instance/haam.db
    python analysis/excerpt_length_eval.py --terms hannibal scipio caesar --lengths 100 140 200
    python analysis/excerpt_length_eval.py --csv out.csv
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "instance" / "haam.db"
DEFAULT_LENGTHS = [60, 100, 140, 200, 280, 400, 600, 100000]
WORD = re.compile(r"[^\W_]+", re.UNICODE)


def excerpt(summary: str, n: int) -> str:
    """Same rule as Event.excerpt in haam/models.py, with a variable limit."""
    summary = summary or ""
    if len(summary) <= n:
        return summary
    return summary[:n].rsplit(" ", 1)[0] + "…"


def words(text: str) -> set[str]:
    return {w.lower() for w in WORD.findall(text or "")}


def load(db: Path):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(
        "select id, title, year, date_label, summary from haam_events where status='approved'"
    ).fetchall()
    con.close()
    return rows


def auto_terms(rows, top: int, min_events: int):
    """Capitalised words from summaries (names), most frequent first."""
    counts: Counter[str] = Counter()
    lower: Counter[str] = Counter()
    for _, _, _, _, summary in rows:
        counts.update({w.lower() for w in re.findall(r"\b[A-Z][a-z]{3,}\b", summary or "")})
        lower.update(set(re.findall(r"\b[a-z]{4,}\b", summary or "")))
    # keep real names: skip words mostly written in lower case ("with", "army")
    return [w for w, c in counts.most_common() if c >= min_events and lower[w] * 2 < c][:top]


def evaluate(rows, terms, lengths):
    truth_words, header_words = [], []
    for _, title, year, date, summary in rows:
        header_words.append(words(f"{title} {date} {year}"))
        truth_words.append(words(summary) | header_words[-1])
    total_pairs = len(rows) * len(terms)
    results = []
    for n in lengths:
        seen = [words(excerpt(r[4], n)) | h for r, h in zip(rows, header_words)]
        tp = fn = fp = 0
        per_term = {}
        for t in terms:
            ttp = sum(1 for s, g in zip(seen, truth_words) if t in s and t in g)
            tfn = sum(1 for s, g in zip(seen, truth_words) if t not in s and t in g)
            tfp = sum(1 for s, g in zip(seen, truth_words) if t in s and t not in g)
            tp, fn, fp = tp + ttp, fn + tfn, fp + tfp
            per_term[t] = (ttp, tfn)
        tn = total_pairs - tp - fn - fp
        size = len(gzip.compress(json.dumps([excerpt(r[4], n) for r in rows]).encode()))
        results.append(dict(limit=n, tp=tp, fn=fn, fp=fp, tn=tn,
                            recall=tp / (tp + fn) if tp + fn else 1.0,
                            precision=tp / (tp + fp) if tp + fp else 1.0,
                            gz_kb=size / 1024, per_term=per_term))
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--lengths", type=int, nargs="+", default=DEFAULT_LENGTHS)
    ap.add_argument("--terms", nargs="*", help="query words; default: most common names in the summaries")
    ap.add_argument("--top", type=int, default=300, help="how many automatic terms")
    ap.add_argument("--min-events", type=int, default=5)
    ap.add_argument("--csv", type=Path, help="write the per-length matrix to this file")
    args = ap.parse_args()

    rows = load(args.db)
    terms = [t.lower() for t in args.terms] if args.terms else auto_terms(rows, args.top, args.min_events)
    print(f"{len(rows)} approved events, {len(terms)} terms: {', '.join(terms[:8])}{'…' if len(terms) > 8 else ''}\n")
    res = evaluate(rows, terms, args.lengths)

    print(f"{'limit':>7} {'TP':>8} {'FN':>8} {'FP':>4} {'TN':>10} {'recall':>8} {'excerpt gz KB':>14}")
    for r in res:
        lim = "full" if r["limit"] >= 100000 else r["limit"]
        print(f"{lim:>7} {r['tp']:>8} {r['fn']:>8} {r['fp']:>4} {r['tn']:>10} {r['recall']:>8.1%} {r['gz_kb']:>14.0f}")

    if args.terms:
        print("\nPer term (found / missed):")
        print(f"{'term':<14}" + "".join(f"{('full' if r['limit'] >= 100000 else r['limit']):>12}" for r in res))
        for t in terms:
            print(f"{t:<14}" + "".join(f"{r['per_term'][t][0]:>6}/{r['per_term'][t][1]:<5}" for r in res))
    else:
        base = res[[r["limit"] for r in res].index(140)] if 140 in args.lengths else res[0]
        print(f"\nTerms most often missed at limit {base['limit']} (found / missed):")
        for t in sorted(terms, key=lambda t: -base["per_term"][t][1])[:10]:
            print(f"  {t:<14}{base['per_term'][t][0]:>6} / {base['per_term'][t][1]}")

    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["limit", "tp", "fn", "fp", "tn", "recall", "precision", "gz_kb"])
            for r in res:
                w.writerow([r["limit"], r["tp"], r["fn"], r["fp"], r["tn"], f"{r['recall']:.4f}", f"{r['precision']:.4f}", f"{r['gz_kb']:.0f}"])
        print(f"\nwrote {args.csv}")


if __name__ == "__main__":
    main()
