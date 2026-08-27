#!/usr/bin/env python3
"""Build data/boards/boards.csv - Ontario's 60 English-language district school boards.

Usage: python3 scripts/build-boards-csv.py

Takes no arguments and, like the other scripts here, resolves the repo root from its own
path so it can be run from any working directory. No dependencies, and no network access:
it reads the vendored Ministry snapshot rather than the live URL, so a build is
reproducible and does not silently change under us when the Ministry republishes.

Input
  data/raw/school-board-contact-list-2026-08-19.csv
      The Ministry of Education's "School board and school authority contact information",
      vendored unmodified from
      https://data.ontario.ca/dataset/school-board-and-school-authority-contact-information
      (resource 74aa6226-7798-4130-ba44-8546e3198186, published 2026-08-19). It is the
      authoritative universe of Ontario boards, sourced from the Board School
      Identification Database. Refresh it by re-downloading to the same path under a new
      dated name and updating SNAPSHOT and SNAPSHOT_RETRIEVED below.

      It is encoded cp1252, not UTF-8 - "Conseil des écoles publiques" is the giveaway.
      None of the 31 boards this script keeps carries a non-ASCII character, but the file
      is decoded properly anyway so that a future widening of scope to the French-language
      boards does not have to rediscover it.

Output
  data/boards/boards.csv
      Generated - do not hand-edit. Written only after every check below passes, so a
      failed run leaves the previous file untouched.

Checks (all fatal)
  - the snapshot still carries the columns this script reads
  - exactly 31 rows are English-language public district school boards. This is the check
    that pins the universe: the count is a published fact about Ontario, so a 30 or a 32
    means the Ministry changed the file's shape or a board was amalgamated, and either way
    the zone registry downstream is now about a different set of boards
  - board_number is unique among them. The snapshot does carry a duplicate row - Grandview
    School Authority appears twice - so this is a real failure mode, not a hypothetical
  - every board named in SUPERVISED matched exactly one row. A stale name here would
    silently drop a covariate the study reports on

SUPERVISION is not in the Ministry file and cannot be derived from it, so it is recorded by
hand below with its source. It is a study covariate rather than a detail: five of these 31
boards are under provincial supervision for the 2026 cycle, with the elected trustees' role
effectively suspended, which is exactly what the survey's DIVISION battery asks about.
"""
import csv
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT = os.path.join(REPO, "data", "raw", "school-board-contact-list-2026-08-19.csv")
SNAPSHOT_RETRIEVED = "2026-08-27"
SNAPSHOT_PUBLISHED = "2026-08-19"
DEST = os.path.join(REPO, "data", "boards", "boards.csv")

# The Ministry's own coding. The language filter is not optional: the two types below also
# cover the 4 French-language public and 8 French-language Catholic boards, which are out
# of scope.
SYSTEM = {"Pub Dist Sch Brd (E/F)": "public", "Cath Dist Sch Brd (E/F)": "catholic"}
BOARD_LANGUAGE = "English"

# Published facts about Ontario, and the reason this script can assert rather than trust.
EXPECTED = {"public": 31, "catholic": 29}

# Boards under provincial supervision for the 2026 cycle, where the role of elected
# trustees is effectively suspended - though at the Catholic boards trustees keep control
# of denominational matters. Named rather than numbered because the Ministry file is the
# only place board numbers appear and a typo there would be invisible; the name match is
# checked below. Source: Global News, "Fewer people running for trustee in some of
# Ontario's supervised school boards", 2026-08-18. All eight are in scope now that the
# English Catholic boards are included.
SUPERVISED_SOURCE = "https://globalnews.ca/news/12025167/ontario-school-trustee-elections/"
SUPERVISED = {
    "Toronto District School Board",
    "Ottawa-Carleton District School Board",
    "Thames Valley District School Board",
    "Near North District School Board",
    "Peel District School Board",
    "Toronto Catholic District School Board",
    "Dufferin-Peel Catholic District School Board",
    "York Catholic District School Board",
}

COLUMNS = ["Region", "Board Number", "Board Name", "Board Language", "Board Type",
           "City", "Website"]

problems = []


def website(raw):
    """Normalise the Website column to something a browser can open.

    Three of the 31 are published without a scheme ('www.ddsb.ca'), which is fine for a
    human reading a directory and useless to anything that follows the link.
    """
    url = (raw or "").strip().rstrip("/")
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


def main():
    if not os.path.exists(SNAPSHOT):
        sys.exit(f"missing snapshot: {SNAPSHOT}\nSee this script's docstring for its source.")

    with open(SNAPSHOT, encoding="cp1252", newline="") as f:
        rows = list(csv.DictReader(f))

    missing = [c for c in COLUMNS if c not in rows[0]]
    if missing:
        problems.append(f"snapshot is missing expected columns: {', '.join(missing)}")
        report()

    boards = [r for r in rows
              if r["Board Type"].strip() in SYSTEM
              and r["Board Language"].strip() == BOARD_LANGUAGE]

    for board_type, system in SYSTEM.items():
        n = sum(1 for r in boards if r["Board Type"].strip() == board_type)
        if n != EXPECTED[system]:
            problems.append(
                f"expected {EXPECTED[system]} English-language {system} district school "
                f"boards, found {n}. Ontario has {EXPECTED[system]}; a different count "
                f"means the snapshot changed shape or the board universe did, and the "
                f"zone registry keyed to it is now about a different set of boards."
            )

    seen = {}
    for r in boards:
        num = r["Board Number"].strip()
        if num in seen:
            problems.append(f"duplicate board_number {num}: "
                            f"{seen[num]!r} and {r['Board Name'].strip()!r}")
        seen[num] = r["Board Name"].strip()

    names = {r["Board Name"].strip() for r in boards}
    for name in sorted(SUPERVISED):
        if name not in names:
            problems.append(
                f"SUPERVISED names a board that is not in the snapshot: {name!r}. "
                f"Fix the name here, or the supervision flag goes missing from the frame."
            )

    if problems:
        report()

    out = []
    for r in sorted(boards, key=lambda x: x["Board Name"].strip()):
        name = r["Board Name"].strip()
        out.append({
            "board_number": r["Board Number"].strip(),
            "board_name": name,
            "system": SYSTEM[r["Board Type"].strip()],
            "region": r["Region"].strip(),
            "city": r["City"].strip(),
            "website": website(r["Website"]),
            "supervised": 1 if name in SUPERVISED else 0,
            "source": "ministry-board-contact-list",
            "source_published": SNAPSHOT_PUBLISHED,
            "retrieved": SNAPSHOT_RETRIEVED,
        })

    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    with open(DEST, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    n_sup = sum(r["supervised"] for r in out)
    n_pub = sum(1 for r in out if r["system"] == "public")
    print(f"wrote {os.path.relpath(DEST, REPO)}: {len(out)} boards "
          f"({n_pub} public, {len(out) - n_pub} Catholic), "
          f"{n_sup} under provincial supervision")
    print(f"  supervision source: {SUPERVISED_SOURCE}")


def report():
    print("build aborted; %d problem(s):" % len(problems), file=sys.stderr)
    for p in problems:
        print("  - " + p, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
