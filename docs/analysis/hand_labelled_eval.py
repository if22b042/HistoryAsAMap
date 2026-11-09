"""Hand-labelled check of the excerpt limit (the 191 events read by hand).

Sample: for each of ten names, up to 20 random events (seed 7) among all
approved events whose full text contains the word; Genghis and Cromwell are
complete. Each was read by a person and labelled
    P  the person took part / is the topic
    M  the person is only mentioned as context
    X  not the person (another person, a place, a thing)
For any limit we then check whether the search would show the event, and scale
the sample counts to the full number of events containing the word.

    python analysis/hand_labelled_eval.py --db ../old/instance/haam.db
"""
from __future__ import annotations

import argparse
import random
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from excerpt_length_eval import DEFAULT_DB, excerpt  # noqa: E402
from relevance_eval import TERMS  # noqa: E402

import gzip, json  # noqa: E402

LIMITS = [100, 140, 200, 300, 400, 600, 100000]

# default label of a sampled event, then exceptions by title.
LABELS = {
    "napoleon": ("P", {"M": ["Battle of Linz-Urfahr", "Battle of Neuwied (1797)", "Treaty of Peterswaldau",
                             "Treaty of Saint Petersburg (1805)", "Battle of Diersheim (1797)", "Treaty of Bucharest (1812)"],
                  "X": ["Battle of Magenta"]}),
    "caesar": ("P", {"M": ["Battle of Ascurum", "Battle of Lauro", "Battle of Utica (49 BC)", "Battle of Lutetia", "Battle of Carteia (46 BC)"],
                     "X": ["Siege of Cefalù (837–838)", "Siege of Byzantium (324)", "Battle of Forum Gallorum", "Battle of Caesar's Camp"]}),
    "alexander": ("X", {"P": ["Cophen campaign", "Siege of the Sogdian Rock"], "M": ["Battle of Ipsus", "Battle of Gabiene"]}),
    "wellington": ("P", {"M": ["Battle of Cogorderos"], "X": ["1942 Wairarapa earthquakes", "Wellington Convention"]}),
    "nelson": ("X", {"P": ["Battle of Trafalgar", "Battle of Cape St. Vincent (1797)", "San Juan Expedition (1780)", "Battle of the Malta Convoy",
                           "Raids on Boulogne", "Assault on Cádiz (1797)", "Action of 19 December 1796",
                           "Battle of Santa Cruz de Tenerife (1797)", "Battle of the Nile", "Battle of Grand Turk"]}),
    "washington": ("X", {"P": ["Siege of Boston"], "M": ["Battle of Staten Island"]}),
    "scipio": ("P", {"M": ["Siege of Carthage (Third Punic War)", "Battle of Insubria", "Mutiny at Sucro"], "X": ["Battle of Wadi Akarit"]}),
    "saladin": ("P", {"X": ["Dujail massacre"]}),
    "genghis": ("P", {"M": ["Siege of Herat (1221)", "Battle of Sanfengshan", "Siege of Ryazan", "Siege of Nishapur (1221)"]}),
    "cromwell": ("P", {"M": ["Treaty of Paris (1657)", "Invasion of Jamaica", "Siege of Limerick (1650–1651)"], "X": ["Pilgrimage of Grace"]}),
}


def label(term: str, title: str) -> str:
    default, exceptions = LABELS[term]
    for lab, titles in exceptions.items():
        if title in titles:
            return lab
    return default


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rows = con.execute("select title, date_label, year, summary from haam_events where status='approved'").fetchall()
    con.close()

    random.seed(7)
    per_term = {}
    for term in TERMS:
        w = re.compile(rf"\b{term}\b", re.I)
        ev = [(t, d, y, s or "") for t, d, y, s in rows if w.search(f"{t} {d} {y} {s or ''}")]
        sample = random.sample([(t, s) for t, _d, _y, s in ev], min(20, len(ev)))
        full_by_title = {t: (d, y) for t, d, y, _s in ev}
        per_term[term] = (len(ev), [(t, s, *full_by_title[t]) for t, s in sample], w)

    sizes = {n: len(gzip.compress(json.dumps([excerpt(r[3], n) for r in rows]).encode())) / 1024 for n in LIMITS}

    print("per term, scaled to every event containing the word: took part (P) found / total, "
          "other-person noise (X) shown\n")
    head = f"{'limit':>6} {'excerpt gz KB':>13}  " + "".join(f"{t[:6]:>9}" for t in TERMS) + "   | macro P-recall  noise(X)  named(P+M)"
    print(head)
    for n in LIMITS:
        cells, recs, noises, named = [], [], [], []
        for term, (N, sample, w) in per_term.items():
            k = N / len(sample)
            tot = {"P": 0, "M": 0, "X": 0}
            shown = {"P": 0, "M": 0, "X": 0}
            for title, summary, d, y in sample:
                lab = label(term, title)
                tot[lab] += 1
                if w.search(f"{title} {d} {y} {excerpt(summary, n)}"):
                    shown[lab] += 1
            recs.append(shown["P"] / tot["P"] if tot["P"] else 0)
            s_all = sum(shown.values())
            noises.append(shown["X"] / s_all if s_all else 0)
            named.append((shown["P"] + shown["M"]) / s_all if s_all else 1)
            cells.append(f"{shown['P'] * k:>4.0f}/{tot['P'] * k:<4.0f}")
        lim = "full" if n >= 100000 else n
        print(f"{lim:>6} {sizes[n]:>13.0f}  " + "".join(f"{c:>9}" for c in cells)
              + f"   | {sum(recs) / len(recs):>12.0%} {sum(noises) / len(noises):>9.0%} {sum(named) / len(named):>10.0%}")
    print("\nterms:", ", ".join(TERMS))


if __name__ == "__main__":
    main()
