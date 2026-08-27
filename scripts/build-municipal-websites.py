#!/usr/bin/env python3
"""Build notes/municipal-websites.csv - a census_id -> official website URL crosswalk.

Usage: python3 scripts/build-municipal-websites.py

No arguments, no dependencies, resolves the repo root from its own path.

WHY THIS EXISTS. Collecting trustee candidates province-wide means visiting the clerk of
every municipality that runs a ballot, and the study's master municipality list carries no
URL column. The Ministry of Municipal Affairs and Housing publishes one, but buried: its
"List of municipalities" CSV puts the URL inside an HTML anchor in the Municipality column,
so the file has to be un-HTMLed before it is a crosswalk.

Inputs
  data/raw/mmah-municipalities-2026-05-26.csv
      Vendored unmodified from https://data.ontario.ca/dataset/municipalities (resource
      6783a586-6b05-4a73-9663-e60a6963c91e, published 2026-05-26). 444 rows: name wrapped
      in an <a href>, municipal status, and geographic area.
  The study's master list at CMB Data/auxiliary-data/Master Municipality List/all_muns.csv,
      read by absolute path, for census_id.

Output
  notes/municipal-websites.csv
      One row per municipality: census_id, csdname, tier, county, website, matched_on.

BOTH INPUTS ARE MIS-ENCODED, in different ways, and both are repaired on the way in by
demojibake().

  The master list MIXES encodings: raw latin-1 bytes (187 occurrences of 0xE9) alongside
  UTF-8 sequences (200 of 0xC3 0xA9) for the same accented characters. No single codec
  reads it: utf-8 raises on the former, latin-1 turns the latter into mojibake.

  MMAH's file is DOUBLE-ENCODED: valid UTF-8 whose code points spell out a latin-1
  misreading, so a correct utf-8 read still yields "Mattice-Val CA(r)tA(c)".

Both are defects in the upstream files rather than things to paper over silently, and both
are worth reporting to their publishers. The repair is applied to the name on each side
before matching, so a municipality with an accent joins on equal terms with one without.

THE JOIN IS BY NAME, which is why matched_on records how each row was matched and why the
script reports every failure rather than dropping it. The two files name municipalities
differently - MMAH writes "Addington Highlands, Township of", the master list writes
"Addington Highlands, Township (TP)" - so both sides are normalised to a bare name before
matching. Where a bare name is not unique in Ontario (there are several), the tier and
county are used to break the tie, and a row that still cannot be matched is printed.

Note that MMAH's 444 rows and the master list's 444 rows are NOT the same 444. Both include
upper-tier counties and regions, which run no ballot of their own; `tier` is carried through
so downstream code can filter to Lower and Single Tier, the 414 that do.
"""
import csv
import html
import os
import re
import sys
import unicodedata

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "data", "raw", "mmah-municipalities-2026-05-26.csv")
MASTER = ('/Users/reed/Can. Mun. Barometer Dropbox/Reed Merrill/cmb_main/CMB Data/'
          'auxiliary-data/Master Municipality List/all_muns.csv')
DEST = os.path.join(REPO, "notes", "municipal-websites.csv")

# Status words either file may append to a name. Stripped from both sides before matching.
STATUS = (r"township|town|city|village|municipality|county|"
          r"united counties|regional municipality|district municipality|"
          r"separated town|of|the corporation")

# MMAH tier values, by whether the municipality runs its own ballot.
BALLOT_TIERS = ("Lower Tier", "Single Tier")

# The status word both files carry, used only to break a tie between two municipalities
# that share a bare name and a tier - Hamilton the single-tier city and Hamilton the
# lower-tier township in Northumberland are the pair that needs it.
STATUS_WORD = re.compile(r"\b(township|town|city|village|municipality)\b", re.I)

# Municipalities the two files genuinely disagree about, rather than spell differently.
# Keyed by census_id, valued by the MMAH name to match. Keep this as short as it is, and
# record why each row is here.
NAME_OVERRIDES = {
    # MMAH carries the post-2020 name; the study's master list still has the pre-amalgamation
    # one. Same municipality, same census subdivision.
    "3557014": "Tarbutt, Township of",
}


def demojibake(s):
    """Repair UTF-8 text that was read as latin-1. See the docstring."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def bare(name):
    """A municipality name reduced to what both files agree on."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.split(",")[0]                      # "Addington Highlands, Township of"
    # A bilingual name joins its halves with a SPACED slash and either half identifies the
    # place. An unspaced slash is part of the name itself, so splitting on a bare "/" would
    # turn "Guelph/Eramosa" into "Guelph" and collide it with the city next door.
    s = re.split(r"\s+/\s+", s)[0]           # "The Nation / La Nation"
    s = re.sub(r"\((?:[A-Z]{1,3})\)", " ", s)  # "(TP)", "(CY)"
    s = s.lower()
    s = re.sub(r"\b(%s)\b" % STATUS, " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    if not os.path.exists(SRC):
        sys.exit(f"missing input: {SRC}\nSee this script's docstring for its source.")

    mmah = []
    with open(SRC, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            cell = r["Municipality"]
            m = re.search(r'href="([^"]+)"', cell)
            name = demojibake(html.unescape(re.sub(r"<[^>]+>", "", cell)).strip())
            mmah.append({
                "name": name,
                "bare": bare(name),
                "website": (m.group(1).strip() if m else ""),
                "tier": r["Municipal status"].strip(),
                "county": r["Geographic area"].strip(),
            })

    master = []
    with open(MASTER, newline="", encoding="latin-1") as f:
        for r in csv.DictReader(f):
            if r.get("province", "").strip() != "35":
                continue
            cid = r["census_id"].strip()
            full = demojibake(r["municipality_name"].strip())
            # csdname is the cleaner of the two columns - it carries no status suffix and,
            # unlike municipality_name, is not mojibake for the accented names.
            name = demojibake((r.get("csdname") or "").strip()) or full.split(",")[0]
            master.append({"census_id": cid,
                           "csdname": name,
                           "full": full,
                           "status": (STATUS_WORD.search(full).group(1).lower()
                                      if STATUS_WORD.search(full) else ""),
                           # a 7-digit census_id is a census subdivision, i.e. a lower- or
                           # single-tier municipality; a 4-digit one is a census division,
                           # i.e. an upper-tier county or region
                           "upper_tier": len(cid) != 7,
                           "bare": bare(name or full)})

    # index MMAH by bare name; keep the list so a duplicate can be spotted rather than
    # silently resolved to whichever row happened to be read first
    by_bare = {}
    for m in mmah:
        by_bare.setdefault(m["bare"], []).append(m)

    by_name = {m["name"]: m for m in mmah}

    out, unmatched, ambiguous = [], [], []
    for mu in master:
        if mu["census_id"] in NAME_OVERRIDES:
            hit = by_name.get(NAME_OVERRIDES[mu["census_id"]])
            if hit:
                out.append({"census_id": mu["census_id"], "csdname": mu["csdname"],
                            "tier": hit["tier"], "county": hit["county"],
                            "website": hit["website"], "matched_on": "override"})
                continue
        cands = by_bare.get(mu["bare"], [])
        if len(cands) == 1:
            hit, how = cands[0], "name"
        elif len(cands) > 1:
            # Several municipalities share a bare name - "Peterborough" is both a city and
            # the county around it. The master list says which: a 7-digit census_id is a
            # census subdivision and so is Lower or Single Tier, a 4-digit one is a census
            # division and so is Upper Tier.
            want_upper = mu["upper_tier"]
            same_tier = [c for c in cands
                         if (c["tier"] not in BALLOT_TIERS) == want_upper]
            if len(same_tier) == 1:
                hit, how = same_tier[0], "name+tier"
            else:
                # Same bare name AND same tier: fall back to the status word, which is what
                # actually distinguishes a city from the township beside it.
                same_status = [c for c in same_tier
                               if mu["status"]
                               and STATUS_WORD.search(c["name"])
                               and STATUS_WORD.search(c["name"]).group(1).lower() == mu["status"]]
                if len(same_status) == 1:
                    hit, how = same_status[0], "name+tier+status"
                else:
                    ambiguous.append((mu, cands))
                    continue
        else:
            unmatched.append(mu)
            continue
        out.append({"census_id": mu["census_id"], "csdname": mu["csdname"],
                    "tier": hit["tier"], "county": hit["county"],
                    "website": hit["website"], "matched_on": how})

    out.sort(key=lambda r: r["csdname"])
    with open(DEST, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    ballot = [r for r in out if r["tier"] in BALLOT_TIERS]
    print(f"wrote {os.path.relpath(DEST, REPO)}: {len(out)} matched of {len(master)}")
    print(f"  running a ballot (Lower/Single Tier): {len(ballot)}")
    print(f"  with a website URL                  : {sum(1 for r in ballot if r['website'])}")
    if ambiguous:
        print(f"\nAMBIGUOUS ({len(ambiguous)}) - bare name matches more than one MMAH row:")
        for mu, cands in ambiguous:
            print(f"  {mu['census_id']} {mu['full'][:38]:<39} -> "
                  f"{[c['name'] + ' / ' + c['county'] for c in cands]}")
    if unmatched:
        print(f"\nUNMATCHED ({len(unmatched)}) - no MMAH row with this bare name:")
        for mu in unmatched:
            print(f"  {mu['census_id']} {mu['full'][:44]:<45} bare={mu['bare']!r}")


if __name__ == "__main__":
    main()
