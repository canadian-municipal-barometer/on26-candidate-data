#!/usr/bin/env python3
"""Derive notes/trustee-zones.csv - one row per trustee contest - from the collected sources.

Usage: python3 scripts/build-trustee-zones.py

No arguments, no dependencies, resolves the repo root from its own path.

THE PROBLEM THIS SOLVES. A trustee zone can span several municipalities, and every one of
their clerks publishes the same contest - with different information. Guelph prints the zone
label "Ward 6, Puslinch" and no vote-for count; Puslinch prints "vote for no more than one"
and no zone label; both list the same two candidates. Counting contests per municipality
would therefore double-count both the contests and their candidates, and would keep whichever
half of the information the first source happened to publish.

HOW TWO CONTESTS ARE RECOGNISED AS ONE. Not by label - the labels disagree, which is the
whole problem. By **board plus candidate set**: nominations closed on 2026-08-21, so a
contest's set of certified candidates is fixed, and two contests of the same board with the
same non-empty candidate set are the same contest. Names are compared normalised (case,
accents, punctuation and word order removed) because clerks publish them in different
shapes - "CHARLES COREY" in one place, "Corey, Charles" in another.

An empty contest cannot be matched this way and is never merged; it stays one row per
municipality, flagged, because "no candidates" is exactly the state a stale page shows.

RESOLVING THE BOARD. A clerk who writes only "English Public School Trustee" leaves the
board to be worked out. Where such a contest's candidate set matches one whose label did
name a board, the board is carried across and recorded as inferred. What is left keeps its
UNRESOLVED-<system> marker so it is visible rather than quietly wrong.

Inputs
  data/raw/trustees/*.json    every harvest (VoterView sweep, Toronto feed, accordion
                              reads), newest file per family. Files with "sections" in the
                              name are the crawler's work queue, not a harvest, and are
                              skipped.
  data/boards/boards.csv
  notes/municipal-websites.csv

Output
  notes/trustee-zones.csv
      board_number, zone_id, seats, n_candidates, zone_labels, municipalities,
      board_source, empty, sources
      zone_id is <board_number>-<slug of the longest label seen>, which is stable as long
      as that label is; it is an identifier, not evidence, and the labels column keeps
      every wording actually published.
"""
import csv
import glob
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARDS = os.path.join(REPO, "data", "boards", "boards.csv")
DEST = os.path.join(REPO, "notes", "trustee-zones.csv")

problems = []


def fold(name):
    """A candidate name reduced to what two clerks would agree on."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    # word order differs between "Last, First" and "First Last" sources
    return " ".join(sorted(w for w in s.split() if w))


def slug(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")[:60]


def harvests():
    """Newest file per harvest family, so a re-run cannot double-count itself."""
    newest = {}
    for f in sorted(glob.glob(os.path.join(REPO, "data", "raw", "trustees", "*.json"))):
        base = os.path.basename(f)
        if "sections" in base:
            continue
        newest[re.sub(r"-\d{4}-\d{2}-\d{2}\.json$", "", base)] = f
    if not newest:
        sys.exit("no harvest found; run one of the scripts/harvest-*.py first")
    out = []
    for f in newest.values():
        try:
            recs = json.load(open(f))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(recs, list):
            out.extend(recs)
    return out


def main():
    boards = {r["board_number"]: r for r in csv.DictReader(open(BOARDS))}
    harvest = harvests()

    # group by (board, candidate set); empty contests get a unique key so they never merge
    groups = defaultdict(list)
    for i, c in enumerate(harvest):
        names = frozenset(fold(x["name_raw"]) for x in c["candidates"])
        key = (c["board_number"], names) if names else (c["board_number"], f"__empty__{i}")
        groups[key].append(c)

    # a contest whose label named no board can borrow one from a contest with the same
    # candidate set that did
    by_names = {}
    for (board, names), items in groups.items():
        if isinstance(names, frozenset) and names and not str(board).startswith(("UNRESOLVED", "AMBIGUOUS")):
            by_names.setdefault(names, set()).add(board)

    rows = []
    for (board, names), items in sorted(groups.items(), key=lambda kv: str(kv[0][0])):
        source = "label"
        if str(board).startswith(("UNRESOLVED", "AMBIGUOUS")) and isinstance(names, frozenset):
            known = by_names.get(names, set())
            if len(known) == 1:
                board, source = next(iter(known)), "inferred-from-candidate-set"
            elif len(known) > 1:
                problems.append(f"candidate set matches {len(known)} different boards: {sorted(known)}")

        labels = sorted({c["office"] for c in items})
        muns = sorted({(c["census_id"], c["csdname"]) for c in items})
        n = len(names) if isinstance(names, frozenset) else 0
        rows.append({
            "board_number": board,
            "zone_id": f"{board}-{slug(max(labels, key=len))}",
            "seats": "",                     # not published by most clerks; filled by hand
            "n_candidates": n,
            "zone_labels": " | ".join(labels),
            "municipalities": " | ".join(f"{cid}:{nm}" for cid, nm in muns),
            "n_municipalities": len(muns),
            "board_source": source,
            "empty": 1 if n == 0 else 0,
            "sources": "harvest",
        })

    rows.sort(key=lambda r: (str(r["board_number"]), r["zone_id"]))
    with open(DEST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    merged = sum(r["n_municipalities"] - 1 for r in rows if r["n_municipalities"] > 1)
    unres = [r for r in rows if str(r["board_number"]).startswith(("UNRESOLVED", "AMBIGUOUS"))]
    inferred = [r for r in rows if r["board_source"] != "label"]
    print(f"wrote {os.path.relpath(DEST, REPO)}")
    print(f"  contests in harvest      : {len(harvest)}")
    print(f"  distinct contests (zones): {len(rows)}   "
          f"({merged} duplicate publications merged away)")
    print(f"  board from label         : {len(rows) - len(unres) - len(inferred)}")
    print(f"  board inferred from set  : {len(inferred)}")
    print(f"  board still unresolved   : {len(unres)}")
    print(f"  empty contests           : {sum(r['empty'] for r in rows)}")
    print(f"  boards represented       : "
          f"{len({r['board_number'] for r in rows if r['board_number'] in boards})} of {len(boards)}")
    for p in problems:
        print("  WARNING:", p)


if __name__ == "__main__":
    main()
