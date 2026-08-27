#!/usr/bin/env python3
"""Harvest Toronto's trustee candidates from the City's own JSON feed.

Usage: python3 scripts/harvest-toronto.py

No arguments, no dependencies beyond curl. Resolves the repo root from its own path.

WHY TORONTO GETS ITS OWN SCRIPT. Toronto is not on VoterView and its candidate page renders
entirely in JavaScript, so both the platform harvest and the general crawler come away with
nothing. It is also the single largest source of trustee candidates in the province, and
the only board that had to be redrawn for 2026 - the province capped boards at 12 trustees
and TDSB was the one board over, cut from 22 wards to 12. Skipping it was not an option.

The page turns out to be a thin shell over a published JSON file, which is a better source
than the rendered page: names arrive already split into firstName/lastName, with email,
phone, social links and a status field. That file is what this reads.

  https://www.toronto.ca/data/elections/candidate_list/trusteeCandidates_2026.json

Structure: {"schoolBoard": [{"id": N, "ward": [{"num": "1", "candidate": [...]}]}]}
where the board id is Toronto's own numbering, mapped to Ministry board numbers by BOARDS
below. Only the two English-language boards are kept; ids 5 and 6 are the French-language
boards and are out of scope.

WITHDRAWN NOMINATIONS. Each candidate carries a `status`. Anything that is not "Active" is
dropped and counted, following the rule the rest of this repo uses: a withdrawn nomination
is not part of the dataset. The count is printed so a change in the feed's vocabulary shows
up as a number rather than as silence.

Output
  data/raw/trustees/toronto-harvest-<date>.json   same record shape as the VoterView harvest
"""
import json
import os
import subprocess
import sys
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://www.toronto.ca/data/elections/candidate_list/trusteeCandidates_2026.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
DEST = os.path.join(REPO, "data", "raw", "trustees",
                    f"toronto-harvest-{date.today().isoformat()}.json")

CENSUS_ID = "3520005"
# Toronto's own school board ids -> Ministry board numbers. The French-language boards
# (5, 6) are deliberately absent: out of scope.
BOARDS = {3: "B66052", 4: "B67059"}
ACTIVE = "Active"


def main():
    r = subprocess.run(["curl", "-sSL", "-A", UA, "--max-time", "45", URL],
                       capture_output=True)
    if r.returncode != 0 or not r.stdout:
        sys.exit(f"could not fetch {URL}")
    try:
        data = json.loads(r.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        sys.exit(f"{URL} did not return JSON: {exc}")

    boards = data.get("schoolBoard")
    if not boards:
        sys.exit("feed has no 'schoolBoard' key; its shape changed - re-read it before trusting this script")

    out, dropped, skipped_boards = [], 0, []
    for b in boards:
        bn = BOARDS.get(b.get("id"))
        if not bn:
            skipped_boards.append(b.get("id"))
            continue
        for ward in b.get("ward", []):
            cands = []
            for c in ward.get("candidate", []):
                if (c.get("status") or "") != ACTIVE:
                    dropped += 1
                    continue
                cands.append({
                    "name_raw": c.get("name", "").strip(),
                    "first_name": (c.get("firstName") or "").strip(),
                    "last_name": (c.get("lastName") or "").strip(),
                    "acclaimed": False,   # the feed carries no acclamation flag
                    "email": (c.get("email") or "").strip(),
                    "phone": (c.get("phone") or "").strip() if c.get("phone") else "",
                    "links": [s.get("url", "") for s in (c.get("socialMedias") or []) if s.get("url")],
                    "nomination_date": (c.get("dateNomination") or "").strip(),
                })
            out.append({
                "census_id": CENSUS_ID, "csdname": "Toronto", "county_mun": "",
                "office": f"Ward {ward.get('num')}",
                "board_number": bn,
                "system": "public" if bn == "B66052" else "catholic",
                "classify_reason": "toronto-feed",
                "empty_notice": not cands,
                "candidates": cands,
            })

    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    json.dump(out, open(DEST, "w"), indent=1)

    nc = sum(len(c["candidates"]) for c in out)
    reach = sum(1 for c in out for x in c["candidates"]
                if x["email"] or x["phone"] or x["links"])
    for bn in sorted({c["board_number"] for c in out}):
        rows = [c for c in out if c["board_number"] == bn]
        print(f"  {bn}: {len(rows):>2} zones, "
              f"{sum(len(c['candidates']) for c in rows):>3} candidates")
    print(f"total: {len(out)} contests, {nc} candidates, "
          f"{reach} reachable ({100 * reach // max(nc, 1)}%)")
    print(f"dropped non-active nominations: {dropped}")
    if skipped_boards:
        print(f"out-of-scope board ids skipped: {skipped_boards}")
    print(f"wrote {os.path.relpath(DEST, REPO)}")


if __name__ == "__main__":
    main()
