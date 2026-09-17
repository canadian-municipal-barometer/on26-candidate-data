#!/usr/bin/env python3
"""Harvest trustee contests from municipalities running the VoterView election platform.

Usage: python3 scripts/harvest-voterview.py [--cache DIR] [--no-fetch]

Takes no required arguments and resolves the repo root from its own path. Only dependency
is curl.

WHAT THIS IS FOR, AND WHAT IT IS NOT. The source of truth for candidates in this repo is
hand-collected (data/raw/by-municipality/, and data/raw/trustees/by-zone/ for trustees).
This script does not write either. It writes ONE file - a harvest - whose job is to make
the hand collection tractable across 414 municipalities instead of 38, and to be diffed
against what a human read off the clerk's page. Treat a disagreement as a question, not as
a correction to apply blindly: VoterView instances go stale (see `empty_notice` below).

HOW IT FINDS MUNICIPALITIES. VoterView serves every municipality on the platform from one
host, keyed by a `countyMun` code. That code is not published anywhere, but it is
derivable: it is the census subdivision's CD number followed by the last two digits of its
CSD number - Mississauga is census 3521005, CD 21 + CSD 05 -> 2105. Verified collision-free
across all 414 Ontario CSDs.

A municipality not on the platform answers with a fixed stub reading only "No candidates
have yet been nominated". A municipality that IS on the platform but has no races posted
answers with the accordion chrome and nothing inside it. The two are told apart by
ON_PLATFORM below, which looks for that chrome. Do not go back to comparing response size:
the two answers differ by ~160 bytes, and reading a cached file in text mode collapses
CRLF to LF and moves the count by more than that.

Match the BUTTON, not its id. The page's jQuery binds a click handler to
`#expandAllCandidateList` whether or not the button was rendered, and as of 2026-09-02
that script block ships with the stub too - so a test for the bare id calls all 414
municipalities members and writes a platform list that would tell the next crawl to skip
every one of them. On 2026-08-27 it did not, which is a change on VoterView's side rather
than a mistake being corrected: the marker has to be something only the rendered chrome
carries.

TEST RECORDS. Three of these instances carry the clerk's own test entry - "TEST TEST",
"TEST2 TEST2", "BAE TEST" - and each would otherwise reach the sampling frame as a person
to invite. A record with TEST as a whole word in its name is refused, and every refusal is
printed so the rule can be audited rather than trusted. Withdrawals, by contrast, VoterView
simply does not publish.

LATE NOMINATION DATES ARE NOT A TEST FOR THIS, and the first version of the rule that used
them was wrong. Nominations closed 2026-08-21, but s. 33(5) of the Municipal Elections Act
reopens them until 2pm on the following Wednesday for any office that drew fewer candidates
than seats - so a trustee nominated on 24 or 26 August is an ordinary candidate in an
under-subscribed race, not an anomaly. The dates are reported at the end of a run and
nothing is dropped on them.

Input
  The master municipality list at CMB Data/auxiliary-data/Master Municipality List/
  all_muns.csv, read by absolute path, filtered to province == "35". Of its 444 Ontario
  rows, only the 414 with a 7-digit census_id are lower- or single-tier municipalities that
  actually run a ballot; the other 30 are counties and regional municipalities and are
  skipped.

Output
  data/raw/trustees/voterview-harvest-<date>.json
      One record per in-scope trustee contest found: census_id, the clerk's own office
      label, the board it resolves to, and the candidates with whatever contact details the
      clerk published.
  notes/voterview-municipalities.csv
      Which municipalities are on the platform at all. Useful on its own: it says which of
      the 414 will need a bespoke read.

Fields worth knowing
  board_number   From scripts/trustee_boards.py. May be UNRESOLVED-<system> when the clerk
                 names only a system ("English Public School Trustee") or AMBIGUOUS-<acr>
                 for an acronym two boards share. Both are resolved later from the
                 municipality, not guessed here.
  empty_notice   The page said "No candidates have yet been nominated". After the
                 2026-08-21 nomination deadline that means the instance is STALE, not that
                 the contest is empty - Ajax is the known case, and its own website carries
                 the real list. Never read this as a zero.
  acclaimed      The page's own Acclaimed marker. VoterView renders the marker hidden when
                 it does not apply, so this checks for a visible one rather than for the
                 word appearing anywhere in the block.
"""
import csv
import json
import os
import re
import html
import subprocess
import sys
import time
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trustee_boards import classify  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = ('/Users/reed/Can. Mun. Barometer Dropbox/Reed Merrill/cmb_main/CMB Data/'
          'auxiliary-data/Master Municipality List/all_muns.csv')
HOST = "ovs.voterview.ca"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
DELAY = 0.25                # be a polite guest on someone else's server

# The accordion's expand/collapse control, as RENDERED. It is emitted for every
# municipality the platform knows about, and absent from the stub returned for one it does
# not, which makes it the reliable test of platform membership. The id alone is not that
# test - the click handler naming it is served to everyone. See the module docstring.
ON_PLATFORM = '<button id="expandAllCandidateList"'

DEST = os.path.join(REPO, "data", "raw", "trustees",
                    f"voterview-harvest-{date.today().isoformat()}.json")
PLATFORM = os.path.join(REPO, "notes", "voterview-municipalities.csv")

NONE_YET = re.compile(r"No candidates have yet been nominated", re.I)

# Nominations closed 2026-08-21; s. 33(5) MEA reopened them to the following Wednesday for
# any office with fewer candidates than seats. Both dates are here to report against, not
# to drop on - see LATE NOMINATION DATES in the module docstring.
NOMINATIONS_CLOSED = date(2026, 8, 21)
NOMINATIONS_REOPENED_UNTIL = date(2026, 8, 26)
# TEST as a whole word. Two of the three test records in this data are named nothing else,
# and the third is "BAE TEST"; no candidate in 414 municipalities carries the word.
TEST_NAME = re.compile(r"\bTEST\d*\b", re.I)


def filed_on(cand):
    """The nomination date as a date, or None if it is absent or unparseable."""
    for fmt in ("%A, %B %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(cand.get("nomination_date", ""), fmt).date()
        except ValueError:
            continue
    return None


def uncertified(cand):
    """Why this record cannot be a certified candidate, or None if it can."""
    if TEST_NAME.search(cand["name_raw"]):
        return "test record"
    return None


def txt(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def municipalities():
    out = []
    with open(MASTER, newline="", encoding="latin-1") as f:
        for r in csv.DictReader(f):
            if r.get("province", "").strip() != "35":
                continue
            cid = r["census_id"].strip()
            if len(cid) != 7 or not cid.isdigit():
                continue        # upper-tier county or region: runs no ballot
            out.append((cid, r["municipality_name"].strip()))
    return out


def fetch(cid, cache, allow_fetch):
    cm = cid[2:4] + cid[4:][-2:]
    path = os.path.join(cache, f"{cid}-{cm}.html") if cache else None
    if path and os.path.exists(path):
        return cm, open(path, encoding="utf-8", errors="replace").read()
    if not allow_fetch:
        return cm, ""
    url = (f"https://{HOST}/candidateList/candidatedetails"
           f"?filter=&countyMun={cm}&schoolcode=")
    r = subprocess.run(["curl", "-sS", "-A", UA, "-H", "X-Requested-With: XMLHttpRequest",
                        "--max-time", "45", url], capture_output=True, text=True)
    doc = r.stdout
    if ON_PLATFORM in doc and path:
        os.makedirs(cache, exist_ok=True)
        open(path, "w", encoding="utf-8").write(doc)
    time.sleep(DELAY)
    return cm, doc


def races(doc):
    """Split the response into races, then each race into candidates."""
    heads = list(re.finditer(
        r'(?is)id="header-(\d+)".*?Candidates for\s*<strong>(.*?)</strong>', doc))
    for k, m in enumerate(heads):
        n, office = m.group(1), txt(m.group(2))
        body = doc[m.end(): heads[k + 1].start() if k + 1 < len(heads) else len(doc)]
        cands, seen = [], set()
        for b in re.split(r'(?is)(?=id="table-%s-toggle-\d+")' % n, body)[1:]:
            nm = re.search(r'(?is)title="([^"]*)"', b)
            if not nm:
                continue
            name = txt(nm.group(1))
            if name in seen:
                continue
            seen.add(name)
            emails = re.findall(r"mailto:([^\"?]+)", b)
            phones = re.findall(r">\s*(\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4})\s*<", b)
            links = re.findall(r'href="(https?://[^"]+)"[^>]*target="candidateSite"', b)
            nomd = re.search(r"(?is)Nomination Date:\s*</strong>\s*([^<]+)", b)
            cands.append({
                "name_raw": name,
                # VoterView keeps the marker in the DOM and hides it when it does not
                # apply, so look for a visible one rather than for the word.
                "acclaimed": bool(re.search(
                    r"(?is)<span(?![^>]*display:\s*none)[^>]*>\s*Acclaimed", b)),
                "email": emails[0].strip() if emails else "",
                "phone": phones[0].strip() if phones else "",
                "links": sorted(set(links)),
                "nomination_date": txt(nomd.group(1)) if nomd else "",
            })
        yield office, cands, bool(NONE_YET.search(body))


def main():
    args = sys.argv[1:]
    cache = None
    if "--cache" in args:
        cache = args[args.index("--cache") + 1]
    allow_fetch = "--no-fetch" not in args

    muns = municipalities()
    harvest, platform, dropped, refused, late = [], [], {}, [], []
    for i, (cid, name) in enumerate(muns, 1):
        cm, doc = fetch(cid, cache, allow_fetch)
        if ON_PLATFORM not in doc:
            continue
        found = list(races(doc))
        platform.append({"census_id": cid, "csdname": name, "county_mun": cm,
                         "n_races": len(found)})
        for office, cands, empty in found:
            keep = []
            for c in cands:
                why = uncertified(c)
                if why:
                    refused.append((cid, name, office, c["name_raw"], why))
                else:
                    keep.append(c)
            cands = keep
            board, system, reason = classify(office)
            if board is None:
                if re.search(r"trustee|school board", office, re.I):
                    dropped.setdefault(reason, []).append(office)
                continue
            for c in cands:
                filed = filed_on(c)
                if filed and filed > NOMINATIONS_CLOSED:
                    late.append((cid, name, c["name_raw"], filed))
            harvest.append({
                "census_id": cid, "csdname": name, "county_mun": cm,
                "office": office, "board_number": board, "system": system,
                "classify_reason": reason, "empty_notice": empty,
                "candidates": cands,
            })
        print(f"{i:>3}/{len(muns)} {cid} {name[:30]:<31} "
              f"races={len(found)} in-scope={sum(1 for o, c, e in found if classify(o)[0])}",
              flush=True)

    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    json.dump(harvest, open(DEST, "w"), indent=1)
    with open(PLATFORM, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["census_id", "csdname", "county_mun", "n_races"])
        w.writeheader()
        w.writerows(sorted(platform, key=lambda r: r["csdname"]))

    nc = sum(len(r["candidates"]) for r in harvest)
    reach = sum(1 for r in harvest for c in r["candidates"]
                if c["email"] or c["phone"] or c["links"])
    pub = sum(1 for r in harvest if r["system"] == "public")
    cat = sum(1 for r in harvest if r["system"] == "catholic")
    unres = sum(1 for r in harvest if str(r["board_number"]).startswith(("UNRESOLVED", "AMBIGUOUS")))
    print(f"\non the platform : {len(platform)} of {len(muns)} municipalities")
    print(f"contests        : {len(harvest)}  ({pub} public, {cat} Catholic, "
          f"{len(harvest) - pub - cat} system unknown)")
    print(f"  needing the municipality->board lookup : {unres}")
    print(f"  stale 'no candidates yet' notices      : {sum(1 for r in harvest if r['empty_notice'])}")
    print(f"candidates      : {nc}   reachable by >=1 channel: {reach} "
          f"({100 * reach // max(nc, 1)}%)")
    if refused:
        print(f"\ndropped records that cannot be certified candidates: {len(refused)}")
        for cid, name, office, who, why in refused:
            print(f"  {cid} {name[:24]:<25} {who[:24]:<25} {why}")
    if late:
        beyond = sum(1 for *_, f in late if f > NOMINATIONS_REOPENED_UNTIL)
        print(f"\ntrustee nominations dated after {NOMINATIONS_CLOSED}: {len(late)} "
              f"({beyond} after the s.33(5) reopening closed on {NOMINATIONS_REOPENED_UNTIL})")
        for cid, name, who, filed in sorted(late, key=lambda r: r[3]):
            print(f"  {cid} {name[:24]:<25} {who[:24]:<25} {filed}")
    if dropped:
        print("\ndropped trustee races:")
        for why, offs in sorted(dropped.items()):
            print(f"  {why}: {len(offs)}")
    print(f"\nwrote {os.path.relpath(DEST, REPO)}")
    print(f"wrote {os.path.relpath(PLATFORM, REPO)}")


if __name__ == "__main__":
    main()
