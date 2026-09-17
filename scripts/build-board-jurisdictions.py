#!/usr/bin/env python3
"""Build notes/board-jurisdictions.csv - which board serves which municipality.

Usage: python3 scripts/build-board-jurisdictions.py

No arguments, no dependencies, resolves the repo root from its own path.

WHAT IT IS FOR. Two jobs, both of which block everything downstream.

  RESOLVING GENERIC LABELS. A clerk who writes only "English Public School Trustee" has
  named a system, not a board. Which board it is follows from which municipality's ballot
  it appeared on - so this crosswalk turns those into real contests instead of leaving them
  as UNRESOLVED-public.

  COMPLETENESS. The 31 English public boards partition Ontario's territory, and so do the
  29 English Catholic boards. Every municipality therefore has AT LEAST one board of each
  system, which is what makes it possible to say whether collection is finished rather than
  merely large: a municipality with no public board on its ballot is a gap.

  It does NOT follow that a municipality has exactly one. The partition is territorial, and
  a municipal boundary can cross a board boundary - so a single ballot can carry two public
  trustee races. Georgian Bay Township is the case in this data: its voters elect a Near
  North trustee or a Trillium Lakelands one depending on where in the township they live.
  A split is recorded as two rows with split=1, not treated as a contradiction.

WHERE THE EVIDENCE COMES FROM. Not from a published crosswalk - none exists. It is read off
what the clerks themselves printed, which is the same evidence a person would use:

  harvest     any harvest under data/raw/trustees/ - the VoterView sweep, Toronto's JSON
              feed, an accordion page - whose race label named the board outright
  crawl       the municipality's own candidate page named the board
  sections    a trustee section extracted from that page carried a board heading
  schools     the Ministry of Education's school list puts a school of that board in that
              municipality (notes/board-municipalities.csv, built by
              scripts/build-board-municipalities.py). This is the only source here that
              does not depend on a clerk having named the board on a web page, and it is
              the one that placed Temagami - whose public board is District School Board
              Ontario North East and not, as its county would suggest, Near North.
  county      INFERRED, not read. See COUNTY INFERENCE below.
  override    notes/board-jurisdiction-overrides.csv - a hand row, with its reason, for a
              municipality whose clerk never names the board at all. Hamilton is the case:
              every race there reads "Ward 3 - English Public". An override carries a
              reason and a source and is the only place a board is asserted rather than
              read, so the file is worth keeping short and worth reading in full.

Both are recorded per row in `evidence`, along with how many independent sources agreed, so
a single-source row can be told from a corroborated one. Rows are NOT invented for
municipalities that named no board; they are simply absent, and the run reports how many.

COUNTY INFERENCE still fills the gap left by clerks who name only a system, and the
ministry school list has cut how much of the file it has to carry - from 329 rows to 88 -
without making it redundant. A municipality with no school of its own is invisible to that
list and can still only be placed from its county.

COUNTY INFERENCE Most Ontario school
board jurisdictions are built out of whole counties and districts, so where every
municipality of a county that HAS been placed agrees on one board of a system, that board
is inferred for the county's remaining municipalities. Without this, a municipality whose
clerk writes only "English Public School Trustee" can never be placed - nothing on its own
page names a board - and its candidates are unattributable.

The inference is conservative and visible:
  - it needs unanimity among the county's placed municipalities, and at least
    MIN_COUNTY_EVIDENCE of them, so one stray reading cannot carry a whole county;
  - it never overrides direct evidence, only fills where there is none;
  - it is stamped `county-inference` in `evidence`, so every inferred row can be found,
    counted, and checked - and any analysis can exclude them in one filter.

It is an inference and it will be wrong somewhere: boards do cross county lines, which is
exactly what the Georgian Bay split below shows. Treat an inferred row as a lead to verify,
not as a reading.

SPLITS ARE KEPT, NOT RESOLVED. Where one municipality claims two boards of a system, both
rows are written with split=1 and the pair is printed for review. Either it is a real split
(Georgian Bay) or one label was misread - and the two are not separable without a human, so
the data says what the sources said. Dropping one would silently lose a real contest, which
is the worse of the two errors: a survey frame that omits a zone cannot be repaired later
by the analyst, while a spurious row is visible and can be deleted.

Inputs
  data/raw/trustees/*harvest*.json  and  data/raw/trustees/accordion-*.json
  notes/municipal-election-pages.csv              boards_found per municipality
  data/raw/trustees/municipal-trustee-sections.json  board per extracted trustee section
  notes/municipal-websites.csv                    the 414 that run a ballot
  data/boards/boards.csv

Output
  notes/board-jurisdictions.csv
      census_id, csdname, county, system, board_number, board_name, split, n_sources,
      evidence
"""
import csv
import glob
import json
import os
import re
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARDS = os.path.join(REPO, "data", "boards", "boards.csv")
SITES = os.path.join(REPO, "notes", "municipal-websites.csv")
PAGES = os.path.join(REPO, "notes", "municipal-election-pages.csv")
SECTIONS = os.path.join(REPO, "data", "raw", "trustees", "municipal-trustee-sections.json")
SCHOOLS = os.path.join(REPO, "notes", "board-municipalities.csv")
OVERRIDES = os.path.join(REPO, "notes", "board-jurisdiction-overrides.csv")
DEST = os.path.join(REPO, "notes", "board-jurisdictions.csv")

BALLOT_TIERS = ("Lower Tier", "Single Tier")

# How many placed municipalities a county needs before its consensus is trusted. Two, so a
# single reading never propagates across a whole county on its own.
MIN_COUNTY_EVIDENCE = 2


def main():
    boards = {r["board_number"]: r for r in csv.DictReader(open(BOARDS))}
    muns = {r["census_id"]: r for r in csv.DictReader(open(SITES))
            if r["tier"] in BALLOT_TIERS}

    # (census_id, system) -> {board_number: {sources}}
    claims = defaultdict(lambda: defaultdict(set))

    # Every harvest counts, not just VoterView: Toronto's feed and the accordion reads name
    # boards the sweep never saw. Keep only the newest file per prefix so a re-run does not
    # double-count itself.
    seen_prefix = {}
    for f in sorted(glob.glob(os.path.join(REPO, "data", "raw", "trustees", "*.json"))):
        base = os.path.basename(f)
        if "sections" in base:
            continue
        seen_prefix[re.sub(r"-\d{4}-\d{2}-\d{2}\.json$", "", base)] = f
    for f in seen_prefix.values():
        try:
            recs = json.load(open(f))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(recs, list):
            continue
        for c in recs:
            bn = c.get("board_number")
            if bn in boards:
                claims[(c["census_id"], boards[bn]["system"])][bn].add("harvest")

    if os.path.exists(PAGES):
        for r in csv.DictReader(open(PAGES)):
            for bn in filter(None, r.get("boards_found", "").split("|")):
                if bn in boards:
                    claims[(r["census_id"], boards[bn]["system"])][bn].add("crawl")

    if os.path.exists(SECTIONS):
        for r in json.load(open(SECTIONS)):
            for sec in r.get("sections", []):
                bn = sec.get("board_number")
                if bn in boards:
                    claims[(r["census_id"], boards[bn]["system"])][bn].add("sections")

    if os.path.exists(SCHOOLS):
        for r in csv.DictReader(open(SCHOOLS)):
            if r["board_number"] in boards:
                claims[(r["census_id"], boards[r["board_number"]]["system"])][
                    r["board_number"]].add("schools")

    if os.path.exists(OVERRIDES):
        for r in csv.DictReader(open(OVERRIDES)):
            if r["board_number"] in boards:
                claims[(r["census_id"], r["system"])][r["board_number"]].add("override")

    # ---- county inference; see COUNTY INFERENCE in the docstring ----
    by_county = defaultdict(lambda: defaultdict(set))
    for (cid, system), found in claims.items():
        if cid in muns and len(found) == 1:
            by_county[(muns[cid]["county"], system)][next(iter(found))].add(cid)

    inferred = 0
    for cid, m in muns.items():
        for system in ("public", "catholic"):
            if claims.get((cid, system)):
                continue                      # direct evidence wins; never override it
            consensus = by_county.get((m["county"], system), {})
            if len(consensus) != 1:
                continue                      # county disagrees, or says nothing
            board, backers = next(iter(consensus.items()))
            if len(backers) < MIN_COUNTY_EVIDENCE:
                continue
            claims[(cid, system)][board].add("county-inference")
            inferred += 1

    rows, splits = [], []
    for (cid, system), found in sorted(claims.items()):
        if cid not in muns:
            continue
        if len(found) > 1:
            splits.append((cid, muns[cid]["csdname"], system, dict(found)))
        for bn, srcs in sorted(found.items()):
            rows.append({"census_id": cid, "csdname": muns[cid]["csdname"],
                         "county": muns[cid]["county"], "system": system,
                         "board_number": bn, "board_name": boards[bn]["board_name"],
                         "split": 1 if len(found) > 1 else 0,
                         "n_sources": len(srcs), "evidence": "|".join(sorted(srcs))})

    rows.sort(key=lambda r: (r["csdname"], r["system"], r["board_number"]))
    with open(DEST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    have = defaultdict(set)
    for r in rows:
        have[r["system"]].add(r["census_id"])
    print(f"wrote {os.path.relpath(DEST, REPO)}: {len(rows)} rows")
    for system in ("public", "catholic"):
        n = len(have[system])
        print(f"  {system:<9}: {n:>3} of {len(muns)} municipalities placed "
              f"({len(muns) - n} still unknown)")
    corroborated = sum(1 for r in rows if r["n_sources"] > 1)
    n_inf = sum(1 for r in rows if r["evidence"] == "county-inference")
    print(f"  corroborated by 2+ sources  : {corroborated}")
    print(f"  read from a source          : {len(rows) - n_inf}")
    print(f"  inferred from county        : {n_inf}  (verify before relying on them)")
    boards_seen = {r["board_number"] for r in rows}
    print(f"  boards reached: {len(boards_seen)} of {len(boards)}")
    missing = [b for b in boards if b not in boards_seen]
    if missing:
        print(f"  boards with NO municipality yet ({len(missing)}):")
        for b in missing:
            print(f"      {b}  {boards[b]['board_name']}")
    if splits:
        print(f"\n  SPLIT MUNICIPALITIES ({len(splits)}) - two boards of one system on one "
              f"ballot. Kept as two rows each; verify each is a real split, not a misread:")
        for cid, name, system, found in splits:
            print(f"      {cid} {name[:24]:<25} {system:<9} "
                  f"{sorted(boards[b]['board_name'] for b in found)}")


if __name__ == "__main__":
    main()
