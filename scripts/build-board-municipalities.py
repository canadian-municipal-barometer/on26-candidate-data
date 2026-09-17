#!/usr/bin/env python3
"""Build notes/board-municipalities.csv - which board operates schools in which municipality.

Usage: python3 scripts/build-board-municipalities.py

No arguments, no dependencies, resolves the repo root from its own path.

WHY THIS EXISTS. notes/board-jurisdictions.csv has to say which board serves which
municipality, because most clerks label a trustee race only by system - "English Public
School Trustee" names no board - and such a contest cannot be attributed without it. Until
now that crosswalk was built from what the clerks themselves printed, plus a county-level
inference to fill the gaps, and roughly half its rows were inferred rather than read. An
inference is a lead, not a reading, and this one is wrong wherever a board crosses a county
line.

There is a better source, and it is authoritative: the Ministry of Education publishes
every school in Ontario with its board AND its municipality. A board that operates a school
in a municipality serves that municipality - that is not an inference, it is a fact about
where the board runs schools, published by the same ministry that defines the boards. Best
of all it is keyed on the SAME board numbers this repo already uses (B28010, B66125), so
there is nothing to match on the board side.

Temagami is why this was worth adding. Its public row had been inferred from its county and
then lost when the evidence set moved; the obvious hand fix is Near North, since Temagami is
in Nipissing District and Near North covers Nipissing. That is wrong. The ministry file
puts Temagami's public school under District School Board Ontario North East, which is one
of the boards this study had no candidates for at all. Every hand-written override is a
guess of that shape waiting to happen.

WHAT IT PROVES, AND WHAT IT DOES NOT. Positive evidence only. A school in a municipality
proves the board serves it; NO school proves nothing, because plenty of small townships
have no school of their own and are still inside some board's jurisdiction. So this file
covers 324 of the 414 ballot-running municipalities and is a floor, not a census - it
replaces guesses where it speaks and stays silent elsewhere, which is why county inference
survives in scripts/build-board-jurisdictions.py rather than being deleted.

It also confirms a split rather than resolving it. Georgian Bay Township has two public
schools, one Near North and one Trillium Lakelands, which is the same split the trustee
harvest found on its ballot - two independent sources agreeing that a municipal boundary
crosses a board boundary there. Two more survive the screen below and are new: Neebing,
whose schools split Keewatin-Patricia and Lakehead either side of Thunder Bay, and Quinte
West, split Hastings & Prince Edward and Kawartha Pine Ridge. Both are leads for the
collection rather than settled facts - a split means a ballot may carry two public trustee
races.

Inputs
  data/raw/sif-school-information-2024-2025.xlsx
      Vendored unmodified from data.ontario.ca, "School information and student
      demographics" (dataset d85f68c5-fcb0-4b4d-aec5-3047db47dcd5, resource
      f75540ed-59eb-49ab-ac43-976d563b3a65, "Preliminary 2024-2025", published 2026-08-18).
      4,947 schools; 4,418 of them belong to one of the 60 English-language district
      boards, the rest to French boards and school authorities that are out of scope.
  notes/municipal-websites.csv    census_id <- municipality name
  data/boards/boards.csv          the 60 boards in scope

Output
  notes/board-municipalities.csv
      One row per (municipality, board) pair, with how many schools and how much enrolment
      back it. n_schools is worth keeping: a board with one school in a municipality and a
      board with 120 are equally real, but the first is the one to double-check if it ever
      contradicts something.

READING XLSX WITHOUT A DEPENDENCY. An .xlsx is a zip of XML, and this file is the simple
case - one sheet, a shared-string table, no formulas or dates. `rows()` below reads it with
zipfile and ElementTree from the standard library, which keeps this script runnable with
nothing installed, like the rest of the pipeline. It is deliberately not a general xlsx
reader; if the ministry ever ships a second sheet or an inline-formatted cell this will
need openpyxl instead.

THE JOIN IS BY NAME, as in scripts/build-municipal-websites.py, and uses the same bare()
normalisation so the two agree. The ministry writes "Sault Ste. Marie, City of" where the
master list writes "Sault Ste. Marie"; stripping the status suffix from both makes them
join. Anything still unmatched is printed rather than dropped silently.

Exactly one bare name is not unique among the 414 ballot-running municipalities: Hamilton,
which is both a single-tier city and a township in Northumberland. The ministry's own
status word CANNOT break that tie, because the ministry uses both values for the city - 136
school rows read "Hamilton, Township of" and every one of them is in the city (L8/L9/L0),
while the 28 that read "Hamilton, City of" are 24 city schools and 4 Kawartha Pine Ridge
schools around Cobourg that belong to the township. The postal code is what actually
separates them, so AMBIGUOUS_BY_POSTAL decides it on the first letter: L is the city, K is
the township. The count of ambiguous names is asserted, so a second one appearing in a
future release stops the run instead of being resolved by a rule written for Hamilton.

THE MUNICIPALITY COLUMN HAS ERRORS IN IT, which is the one thing to know before trusting
this file. They are not encoding problems, they are wrong values:

    St James Major, in Sharbot Lake (K0H2P0, Frontenac), is labelled "Essex, County of"
    St Martin of Tours, in Whitney (K0J2M0, Nipissing), is labelled "Timmins, City of"
    four Kawartha Pine Ridge schools around Cobourg are labelled "Hamilton, City of"
      when they are in Hamilton TOWNSHIP, Northumberland - a different municipality

Left alone these invent jurisdictions: they would put Algonquin and Lakeshore Catholic on
Essex's and Timmins' ballots and Kawartha Pine Ridge on Hamilton the city's. So a pair is
screened against the geography the same file publishes: every school carries a postal code,
and each of the errors is a school hundreds of kilometres from the municipality it is filed
under.

THE SCREEN IS ONE POSTAL LETTER, AT COUNTY LEVEL. A postal code's first letter covers a
large region of Ontario - K the east, L the Golden Horseshoe, M Toronto, N the southwest, P
the north - and every error above crosses one of those boundaries while every true pair
stays inside it. A (municipality, board) pair is kept if its schools' postal letter is one
that at least MIN_COUNTY_SCHOOLS of the county's schools also carry.

Both halves of that were arrived at by being wrong first, and both are worth keeping:

  County, not municipality. A municipality can have exactly ONE matched school, and then
  its own mislabel is the only evidence of where it is and certifies itself. Alfred and
  Plantagenet, in Prescott and Russell, had one matched school: Nottingham Public School,
  in AJAX. Enniskillen was worse - a municipality-level screen kept a stray Kawartha Pine
  Ridge school and dropped Enniskillen's real Lambton Kent one, because the stray was the
  modal prefix of a set of size one.

  One letter, not two, and a flat floor rather than a share of the county. Two characters
  plus a 5% share dropped eight true pairs: East Gwillimbury and King are L0/L7 inside an
  L4-dominated York Region, Scugog and Uxbridge are L9 inside L1-dominated Durham, and
  Espanola is P5 inside P3-dominated Sudbury. A small municipality's postal district is
  always a small share of a big county, so a share threshold penalises exactly the
  municipalities this file exists to place.

ONE TRUE PAIR IS STILL LOST TO THIS, and it is the honest cost: South Algonquin's Renfrew
County DSB school is K0J, because the township sits on the Renfrew border, while the rest
of Nipissing District is P. The county has no second K school to clear the floor with, so
the pair is dropped. It is printed with the rest, and Renfrew County DSB is placed in South
Algonquin anyway by the crawl, which read the board's name off the township's own page.

The screen is deliberately weaker than dropping every municipality served by two boards of
one system, which would have been the easy rule and would have thrown away the best finding
in the file: Georgian Bay Township really is split, Near North at Mactier (P0C) and
Trillium Lakelands at Honey Harbour (P0E), both inside the township and both ordinary for
Muskoka. That is the same split the trustee harvest sees on Georgian Bay's ballot, from an
independent source. A rule that could not tell it from the Sharbot Lake error would be
losing the row worth knowing about.
"""
import collections
import csv
import os
import re
import sys
import unicodedata
import zipfile
from xml.etree import ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "data", "raw", "sif-school-information-2024-2025.xlsx")
SITES = os.path.join(REPO, "notes", "municipal-websites.csv")
BOARDS = os.path.join(REPO, "data", "boards", "boards.csv")
DEST = os.path.join(REPO, "notes", "board-municipalities.csv")

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# Same normalisation as scripts/build-municipal-websites.py - keep the two in step.
STATUS = (r"township|town|city|village|municipality|county|"
          r"united counties|regional municipality|district municipality|"
          r"separated town|of|the corporation")
STATUS_WORD = re.compile(r"\b(township|town|city|village|municipality)\b", re.I)
BALLOT_TIERS = ("Lower Tier", "Single Tier")

# The one bare name two ballot-running municipalities share, and the postal letter that
# tells them apart. See THE JOIN IS BY NAME. Keyed by bare name -> {postal letter: census_id}.
AMBIGUOUS_BY_POSTAL = {
    "hamilton": {"L": "3525005",     # Hamilton, the single-tier city
                 "K": "3514019"},    # Hamilton, the township in Northumberland
}

# How many of a county's schools have to share a postal letter before a pair sitting in
# that letter is believed. Two, so a single mislabel can never certify itself, and flat
# rather than a share of the county - see THE SCREEN IS ONE POSTAL LETTER.
MIN_COUNTY_SCHOOLS = 2


def _col(ref):
    """Column index from a cell reference: 'A'->0, 'AB'->27."""
    m = re.match(r"([A-Z]+)", ref or "")
    n = 0
    for ch in (m.group(1) if m else "A"):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def rows(path, sheet="xl/worksheets/sheet1.xml"):
    """Yield each row of a simple xlsx as a list of strings. See READING XLSX above."""
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
    for _, row in ET.iterparse(z.open(sheet), events=("end",)):
        if row.tag != NS + "row":
            continue
        out = []
        for c in row.findall(NS + "c"):
            i = _col(c.get("r"))
            while len(out) <= i:
                out.append("")
            t, v = c.get("t"), c.find(NS + "v")
            if t == "s" and v is not None:
                out[i] = shared[int(v.text)]
            elif t == "inlineStr":
                isx = c.find(NS + "is")
                out[i] = ("".join(x.text or "" for x in isx.iter(NS + "t"))
                          if isx is not None else "")
            else:
                out[i] = v.text if v is not None else ""
        yield out
        row.clear()


def bare(name):
    """A municipality name reduced to what both files agree on."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.split(",")[0]
    s = re.split(r"\s+/\s+", s)[0]
    s = re.sub(r"\((?:[A-Z]{1,3})\)", " ", s).lower()
    s = re.sub(r"\b(%s)\b" % STATUS, " ", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def main():
    if not os.path.exists(SRC):
        sys.exit(f"missing input: {SRC}\nSee this script's docstring for its source.")

    boards = {r["board_number"]: r for r in csv.DictReader(open(BOARDS))}
    sites = list(csv.DictReader(open(SITES)))
    ballot = [r for r in sites if r["tier"] in BALLOT_TIERS]
    by_id = {r["census_id"]: r for r in sites}
    by_bare = collections.defaultdict(list)
    for r in ballot:
        by_bare[bare(r["csdname"])].append(r)

    # A rule written for Hamilton must not silently resolve some other collision.
    shared = sorted(k for k, v in by_bare.items() if len(v) > 1)
    if shared != sorted(AMBIGUOUS_BY_POSTAL):
        sys.exit("bare municipality names shared by two ballot-running municipalities have "
                 f"changed: {shared}. AMBIGUOUS_BY_POSTAL covers "
                 f"{sorted(AMBIGUOUS_BY_POSTAL)}; add the new one (with the postal letter "
                 "that separates them) before trusting this join.")

    it = rows(SRC)
    hdr = next(it)
    try:
        iB = hdr.index("Board Number")
        iM = hdr.index("Municipality")
        iE = hdr.index("Enrolment")
        iP = hdr.index("Postal Code")
    except ValueError:
        sys.exit(f"unexpected columns in {os.path.basename(SRC)}: {hdr[:8]}")

    pairs = collections.defaultdict(lambda: {"n": 0, "enrol": 0, "fsa": collections.Counter()})
    n_rows = n_scope = 0
    unmatched = collections.Counter()
    for r in it:
        if not any(r):
            continue
        n_rows += 1
        bn = r[iB].strip()
        if bn not in boards:
            continue                       # French board or school authority: out of scope
        n_scope += 1
        raw = r[iM].strip()
        postal = re.sub(r"[^A-Z0-9]", "", (r[iP] or "").upper())
        key = bare(raw)
        hits = by_bare.get(key, [])
        if len(hits) > 1:
            # See THE JOIN IS BY NAME: the postal code separates them, the status word does not.
            want = AMBIGUOUS_BY_POSTAL.get(key, {}).get(postal[:1], "")
            hits = [h for h in hits if h["census_id"] == want]
        if len(hits) != 1:
            unmatched[raw or "(blank)"] += 1
            continue
        h = hits[0]
        p = pairs[(h["census_id"], h["csdname"], h["county"], bn)]
        p["n"] += 1
        if postal[:1]:
            p["fsa"][postal[:1]] += 1
        try:
            p["enrol"] += int(float(r[iE] or 0))
        except (ValueError, TypeError):
            pass

    # Where is each county? Every postal region its schools sit in, with a count. See THE
    # MUNICIPALITY COLUMN HAS ERRORS IN IT for why this is at county and not municipal level.
    where = collections.defaultdict(collections.Counter)
    for (_cid, _n, county, _b), p in pairs.items():
        where[county].update(p["fsa"])

    out, mislabelled = [], []
    for (cid, name, county, bn), p in pairs.items():
        seen_here = where[county]
        ok = [f for f in p["fsa"] if seen_here[f] >= MIN_COUNTY_SCHOOLS]
        if p["fsa"] and not ok:
            mislabelled.append((cid, name, county, bn, boards[bn]["board_name"], p["n"],
                                sorted(p["fsa"]),
                                ",".join(f"{f}({n})" for f, n in seen_here.most_common(4))))
            continue
        out.append({"census_id": cid, "csdname": name, "county": county,
                    "system": boards[bn]["system"], "board_number": bn,
                    "board_name": boards[bn]["board_name"],
                    "n_schools": p["n"], "enrolment": p["enrol"]})
    out.sort(key=lambda r: (r["csdname"], r["system"], -r["n_schools"]))
    with open(DEST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    placed = collections.defaultdict(set)
    for r in out:
        placed[r["system"]].add(r["census_id"])
    print(f"wrote {os.path.relpath(DEST, REPO)}: {len(out)} (municipality, board) pairs")
    print(f"  schools read                 : {n_rows}")
    print(f"  in one of the 60 English boards: {n_scope}")
    print(f"  municipalities covered       : {len({r['census_id'] for r in out})} "
          f"of {len(ballot)} that run a ballot")
    for system in ("public", "catholic"):
        print(f"    {system:<9}: {len(placed[system]):>3} municipalities, "
              f"{len({r['board_number'] for r in out if r['system'] == system})} boards")
    missing = sorted(b for b in boards if b not in {r["board_number"] for r in out})
    print(f"  boards covered               : {len(boards) - len(missing)} of {len(boards)}")
    for b in missing:
        print(f"      no schools matched: {b} {boards[b]['board_name']}")

    # A municipality with two boards of one system is a split - the same thing the trustee
    # harvest sees on a ballot, and worth printing because it contradicts the tidy picture.
    two = collections.defaultdict(list)
    for r in out:
        two[(r["census_id"], r["system"])].append(r)
    splits = {k: v for k, v in two.items() if len(v) > 1}
    if splits:
        print(f"\n  municipalities served by 2+ boards of ONE system ({len(splits)}) - "
              f"a board boundary crossing a municipal one:")
        for (cid, system), rs in sorted(splits.items(), key=lambda x: x[1][0]["csdname"]):
            names = ", ".join(f"{r['board_name'].split(' District')[0]}({r['n_schools']})"
                              for r in sorted(rs, key=lambda r: -r["n_schools"]))
            print(f"      {cid} {rs[0]['csdname'][:24]:<25} {system:<9} {names}")

    if mislabelled:
        print(f"\n  pairs dropped as mislabelled ({len(mislabelled)}) - the board's schools "
              f"sit in a different postal region than the municipality's other schools, so "
              f"the ministry's Municipality value is wrong:")
        for cid, name, county, bn, bname, n, fsas, home in sorted(mislabelled,
                                                                   key=lambda x: x[1]):
            print(f"      {cid} {name[:20]:<21} {bn} {bname[:34]:<35} "
                  f"{n} school(s) in {','.join(fsas)}; {county[:16]} is {home}")

    if unmatched:
        print(f"\n  school rows whose municipality did not join ({sum(unmatched.values())} "
              f"rows, {len(unmatched)} names):")
        for k, v in unmatched.most_common(20):
            print(f"      {v:>4}  {k}")


if __name__ == "__main__":
    main()
