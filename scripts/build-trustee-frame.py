#!/usr/bin/env python3
"""Build data/csv/trustee-candidate-frame.csv - the survey sampling frame.

Usage: python3 scripts/build-trustee-frame.py

No arguments, no dependencies, resolves the repo root from its own path.

WHAT THIS IS. One row per trustee candidate for Ontario's 60 English-language district
school boards, carrying the contact details needed to invite them to the CMB's 2026 School
Board Trustee Candidate Survey and the board metadata needed to analyse their answers. It
is a frame, not a Qualtrics respondent list: nothing here is served to respondents.

The survey itself asks nothing about which board a respondent runs for, so board, system
and supervised status exist ONLY because this file carries them. They are the covariates
the study's central questions turn on - the DIVISION battery on provincial-vs-trustee
power, and the item "The number of trustees per board should be capped at 12".

DEDUPLICATION IS THE POINT, not a detail. A trustee zone can span several municipalities
and every clerk in it publishes the same contest, so a naive concatenation of sources
double-counts candidates. Rows are keyed on (board_number, folded candidate name) and
merged across every source, with the municipalities each was seen in kept in
`seen_in_municipalities`. Contact fields are filled from the first source that has them,
and `contact_source` records which.

WITHDRAWN NOMINATIONS never reach here: each harvester drops them at its own source, which
is where the marker is legible.

Inputs
  data/raw/trustees/*.json        every harvest (VoterView sweep, Toronto feed, accordion
                                  reads). Files with "sections" in the name are the
                                  crawler's work queue, not a harvest, and are skipped.
  data/boards/boards.csv
  notes/board-jurisdictions.csv   resolves UNRESOLVED-<system> labels to a board
  notes/municipal-websites.csv

Output
  data/csv/trustee-candidate-frame.csv

COVERAGE IS REPORTED, NOT ASSUMED. The run prints how many of the 60 boards are
represented, how many candidates are reachable by at least one channel, and the same broken
out by board. A frame nobody can be contacted through is not a frame, and that number
belongs in front of whoever decides to field the survey.
"""
import csv
import glob
import json
import os
import re
import unicodedata
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARDS = os.path.join(REPO, "data", "boards", "boards.csv")
JURIS = os.path.join(REPO, "notes", "board-jurisdictions.csv")
SITES = os.path.join(REPO, "notes", "municipal-websites.csv")
DEST = os.path.join(REPO, "data", "csv", "trustee-candidate-frame.csv")


def fold(name):
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(sorted(w for w in s.split() if w))


def main():
    boards = {r["board_number"]: r for r in csv.DictReader(open(BOARDS))}
    muns = {r["census_id"]: r for r in csv.DictReader(open(SITES))}

    juris = defaultdict(list)
    if os.path.exists(JURIS):
        for r in csv.DictReader(open(JURIS)):
            juris[(r["census_id"], r["system"])].append(r["board_number"])

    # newest file per harvest family, so a re-run cannot double-count itself
    newest = {}
    for f in sorted(glob.glob(os.path.join(REPO, "data", "raw", "trustees", "*.json"))):
        base = os.path.basename(f)
        if "sections" in base:
            continue
        newest[re.sub(r"-\d{4}-\d{2}-\d{2}\.json$", "", base)] = f

    merged, unresolved = {}, 0
    for src, path in sorted(newest.items()):
        try:
            recs = json.load(open(path))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(recs, list):
            continue
        for c in recs:
            board = c.get("board_number")
            system = c.get("system")
            if str(board).startswith(("UNRESOLVED", "AMBIGUOUS")):
                known = juris.get((c["census_id"], system or ""), [])
                if len(known) == 1:
                    board = known[0]
                else:
                    unresolved += len(c.get("candidates") or [])
                    continue
            if board not in boards:
                continue
            b = boards[board]
            for cand in c.get("candidates") or []:
                key = (board, fold(cand.get("name_raw", "")))
                if not key[1]:
                    continue
                row = merged.get(key)
                if row is None:
                    row = merged[key] = {
                        "board_number": board, "board_name": b["board_name"],
                        "system": b["system"], "supervised": b["supervised"],
                        "zone_labels": set(), "seen_in_municipalities": set(),
                        "name_raw": cand.get("name_raw", ""),
                        "first_name": cand.get("first_name", ""),
                        "last_name": cand.get("last_name", ""),
                        "acclaimed": 0, "email": "", "phone": "", "website": "",
                        "contact_source": "", "sources": set(),
                    }
                row["zone_labels"].add(c.get("office", ""))
                row["seen_in_municipalities"].add(
                    f"{c['census_id']}:{muns.get(c['census_id'], {}).get('csdname', c.get('csdname',''))}")
                row["sources"].add(src)
                row["acclaimed"] = max(row["acclaimed"], 1 if cand.get("acclaimed") else 0)
                for field, val in (("email", cand.get("email")),
                                   ("phone", cand.get("phone"))):
                    if val and not row[field]:
                        row[field] = val
                        row["contact_source"] = row["contact_source"] or src
                links = cand.get("links") or []
                if links and not row["website"]:
                    row["website"] = links[0]
                    row["contact_source"] = row["contact_source"] or src

    rows = []
    for row in merged.values():
        r = dict(row)
        r["zone_labels"] = " | ".join(sorted(x for x in row["zone_labels"] if x))
        r["seen_in_municipalities"] = " | ".join(sorted(row["seen_in_municipalities"]))
        r["n_municipalities"] = len(row["seen_in_municipalities"])
        r["sources"] = " | ".join(sorted(row["sources"]))
        r["reachable"] = 1 if (r["email"] or r["phone"] or r["website"]) else 0
        rows.append(r)

    order = ["board_number", "board_name", "system", "supervised", "zone_labels",
             "name_raw", "first_name", "last_name", "acclaimed",
             "email", "phone", "website", "reachable", "contact_source",
             "seen_in_municipalities", "n_municipalities", "sources"]
    rows.sort(key=lambda r: (r["board_name"], r["zone_labels"], r["name_raw"]))

    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    with open(DEST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=order)
        w.writeheader()
        w.writerows([{k: r[k] for k in order} for r in rows])

    reach = sum(r["reachable"] for r in rows)
    em = sum(1 for r in rows if r["email"])
    seen = {r["board_number"] for r in rows}
    print(f"wrote {os.path.relpath(DEST, REPO)}")
    print(f"  candidates            : {len(rows)}")
    print(f"  with email            : {em} ({100 * em // max(len(rows),1)}%)")
    print(f"  reachable (any channel): {reach} ({100 * reach // max(len(rows),1)}%)")
    print(f"  acclaimed             : {sum(r['acclaimed'] for r in rows)}")
    print(f"  boards represented    : {len(seen)} of {len(boards)}")
    print(f"  candidates dropped, board unresolved: {unresolved}")
    print(f"\n  by system:")
    for system in ("public", "catholic"):
        rs = [r for r in rows if r["system"] == system]
        rr = sum(r["reachable"] for r in rs)
        print(f"    {system:<9} {len(rs):>4} candidates, {rr:>4} reachable "
              f"({100 * rr // max(len(rs),1)}%), "
              f"{len({r['board_number'] for r in rs})} boards")
    missing = sorted(b for b in boards if b not in seen)
    if missing:
        print(f"\n  boards with NO candidates yet ({len(missing)}):")
        for b in missing:
            print(f"      {b}  {boards[b]['board_name']}")


if __name__ == "__main__":
    main()
