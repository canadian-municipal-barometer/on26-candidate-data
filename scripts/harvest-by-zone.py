#!/usr/bin/env python3
"""Turn the hand-collected trustee files in data/raw/trustees/by-zone/ into a harvest.

Usage: python3 scripts/harvest-by-zone.py [--out FILE]

No dependencies, resolves the repo root from its own path.

WHY THIS EXISTS. Every other harvester in this repo reads a machine-readable source: an
undocumented VoterView endpoint, Toronto's JSON feed, a saved HTML page. Some clerks
publish a list that none of those can reach, and for those the collection is done by hand -
that is what data/raw/trustees/by-zone/ is for, and it is the trustee counterpart of
data/raw/by-municipality/ for council. This script does nothing but restate those files in
the harvest schema, so scripts/build-trustee-frame.py picks them up on the same footing as
a scrape and the deduplication in that script works across the two.

It is deliberately a thin translator. All the judgement - which board a zone belongs to,
whether a candidate was acclaimed, whether a name on the page is a withdrawal - is made
once, by a person, in the by-zone file, where the reasoning can be written down next to it.
Nothing here infers anything.

WHAT A BY-ZONE FILE LOOKS LIKE. One file per municipality, named <census_id>-<slug>.json,
mirroring data/raw/by-municipality/:

    census_id, csdname            which municipality's clerk published the list
    name_format                   how the source writes names, as in by-municipality/
    candidate_list_url            the page it was read from
    notes                         free-form, and the point of the file: why it had to be
                                  read by hand, what the page's own quirks are, and a
                                  `retrieved` date
    contests[]                    one per (board, zone), each with
        board_number              a real board id - NOT an UNRESOLVED-<system> label. A
                                  person reading a page can see which board a zone belongs
                                  to; there is nothing for the crosswalk to resolve.
        system                    "public" or "catholic", and it must agree with the board
        office                    the zone as the source labels it, e.g.
                                  "Zone 1 (Wards 5, 6, 21)"
        candidates[]              name_raw, acclaimed, email, phone, links[]

THE CHECKS ARE THE VALUE. A hand-written file is the one input with no upstream format to
keep it honest, so this refuses rather than passes along: an unknown board id, a system
that disagrees with the board's, a contest with no candidates, a duplicate name inside one
contest, a name that is blank or one word, and any name still carrying a WITHDRAWN or
ACCLAIMED marker - the marker belongs in the `acclaimed` field, and a withdrawal does not
belong in this dataset at all. Every failure names the file and the contest.

Input
  data/raw/trustees/by-zone/*.json
  data/boards/boards.csv          the 60 boards, to check board_number and system

Output
  data/raw/trustees/by-zone-harvest-<date>.json
      The harvest family name is "by-zone-harvest", so build-trustee-frame.py keeps only
      the newest dated file and a re-run cannot double-count itself.
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
import unicodedata
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "data", "raw", "trustees", "by-zone")
BOARDS = os.path.join(REPO, "data", "boards", "boards.csv")

# A marker that belongs in a field, not in a name. Both are stripped and normalised by the
# other harvesters; a by-zone file is written by hand, so here they are an error instead.
STATUS_IN_NAME = re.compile(r"\b(withdrawn|acclaimed|acclamation)\b", re.I)


def fold(name):
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return " ".join(sorted(w for w in re.sub(r"[^a-z0-9 ]+", " ", s).split() if w))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args()

    boards = {r["board_number"]: r for r in csv.DictReader(open(BOARDS))}
    files = sorted(glob.glob(os.path.join(SRC, "*.json")))
    if not files:
        sys.exit(f"no by-zone files in {os.path.relpath(SRC, REPO)} - nothing to do")

    out, errors = [], []
    for path in files:
        rel = os.path.relpath(path, REPO)
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"{rel}: unreadable ({exc})")
            continue

        cid = str(doc.get("census_id") or "")
        name = doc.get("csdname") or ""
        url = doc.get("candidate_list_url") or ""
        retrieved = (doc.get("notes") or {}).get("retrieved", "")
        if not cid:
            errors.append(f"{rel}: no census_id")
            continue
        if not retrieved:
            errors.append(f"{rel}: notes.retrieved is missing - a hand-read list has to "
                          f"say when it was read")

        for con in doc.get("contests") or []:
            where = f"{rel} [{con.get('office', '?')}]"
            bn, system = con.get("board_number"), con.get("system")
            if bn not in boards:
                errors.append(f"{where}: board_number {bn!r} is not one of the 60 boards")
                continue
            if system != boards[bn]["system"]:
                errors.append(f"{where}: system {system!r} disagrees with {bn} "
                              f"({boards[bn]['board_name']} is {boards[bn]['system']})")
                continue
            cands, seen = [], set()
            for c in con.get("candidates") or []:
                nm = (c.get("name_raw") or "").strip()
                if not nm or len(nm.split()) < 2:
                    errors.append(f"{where}: {nm!r} is not a name")
                    continue
                if STATUS_IN_NAME.search(nm):
                    errors.append(f"{where}: {nm!r} carries a status marker in the name - "
                                  f"put it in `acclaimed`, or drop a withdrawal entirely")
                    continue
                if fold(nm) in seen:
                    errors.append(f"{where}: {nm!r} appears twice in one contest")
                    continue
                seen.add(fold(nm))
                cands.append({
                    "name_raw": nm,
                    "acclaimed": bool(c.get("acclaimed")),
                    "email": (c.get("email") or "").strip(),
                    "phone": (c.get("phone") or "").strip(),
                    "links": [l for l in (c.get("links") or []) if l],
                })
            if not cands:
                errors.append(f"{where}: no candidates")
                continue
            out.append({
                "census_id": cid, "csdname": name, "county_mun": "",
                "office": con.get("office", ""),
                "board_number": bn, "system": system,
                "classify_reason": "by-zone-hand-collected",
                "source_url": url, "retrieved": retrieved,
                "empty_notice": False,
                "candidates": cands,
            })

    if errors:
        print(f"REFUSING TO WRITE - {len(errors)} problem(s) in the by-zone files:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)

    dest = a.out or os.path.join(REPO, "data", "raw", "trustees",
                                 f"by-zone-harvest-{date.today().isoformat()}.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    json.dump(out, open(dest, "w"), indent=1, ensure_ascii=False)

    nc = sum(len(c["candidates"]) for c in out)
    reach = sum(1 for c in out for x in c["candidates"]
                if x["email"] or x["phone"] or x["links"])
    print(f"read {len(files)} by-zone file(s) from "
          f"{len({c['census_id'] for c in out})} municipalities")
    for bn in sorted({c["board_number"] for c in out}):
        rows = [c for c in out if c["board_number"] == bn]
        print(f"  {bn} {boards[bn]['board_name'][:44]:<45} {len(rows):>2} zones, "
              f"{sum(len(c['candidates']) for c in rows):>3} candidates, "
              f"{sum(1 for c in rows for x in c['candidates'] if x['acclaimed']):>2} acclaimed")
    print(f"total: {len(out)} contests, {nc} candidates, "
          f"{reach} reachable ({100 * reach // max(nc, 1)}%)")
    print(f"wrote {os.path.relpath(dest, REPO)}")


if __name__ == "__main__":
    main()
