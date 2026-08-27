"""Resolve a clerk's trustee race label to one of Ontario's 60 English district school boards.

Usage (as a module):
    from trustee_boards import classify
    board_number, system, reason = classify("Trustee - GECDSB - Wards 1, 2 & 9")

Clerks label the same contest a dozen different ways. Three shapes appear in the data:

  1. the board's full name       "Upper Grand District School Board Trustee - Wards 1 and 5"
  2. the board's acronym         "Trustee - GECDSB - Wards 1, 2 & 9"
  3. a generic system label      "English Public School Trustee"

Only the first two identify a board. The third identifies a *system*, and is resolved by
looking up which board of that system serves the municipality - that is what
notes/board-jurisdictions.csv is for. classify() returns UNRESOLVED-<system> for those
rather than guessing, so the caller has to do the lookup.

WHY THIS IS A WHITELIST AND NOT A PATTERN. The obvious rule - "a C in the acronym means
Catholic" - is wrong in both directions. GECDSB (Greater Essex County) and RCDSB (Renfrew
County) are public boards whose C stands for County. Meanwhile "London District Catholic
School Board" is LDCSB, with the C in the middle. Every acronym is therefore listed against
its board by hand.

AMBIGUOUS ACRONYMS. Two acronyms are genuinely used by two boards each:
  SCDSB - Simcoe County DSB (public) and Sudbury Catholic DSB
  WCDSB - Waterloo Catholic DSB and Wellington Catholic DSB
They are listed in AMBIGUOUS rather than against either board, and classify() returns
AMBIGUOUS-<acronym> for them. Resolving one needs the municipality, so it is the caller's
job and not a coin flip here. A label carrying the full board name is unaffected, because
full names are matched before acronyms.
"""
import re

# board_number -> (system, canonical name, [acronyms and distinctive name stems])
BOARDS = {
 # ---- English-language public (31) ----
 "B28010": ("public", "Algoma District School Board", ["ADSB", "Algoma"]),
 "B66010": ("public", "Avon Maitland District School Board", ["AMDSB", "Avon Maitland"]),
 "B66001": ("public", "Bluewater District School Board", ["BWDSB", "Bluewater"]),
 "B28002": ("public", "District School Board Ontario North East", ["DSB1", "Ontario North East"]),
 "B66150": ("public", "District School Board of Niagara", ["DSBN", "District School Board of Niagara"]),
 "B66060": ("public", "Durham District School Board", ["DDSB", "Durham District School Board"]),
 "B66168": ("public", "Grand Erie District School Board", ["GEDSB", "Grand Erie"]),
 "B66028": ("public", "Greater Essex County District School Board", ["GECDSB", "Greater Essex"]),
 "B66133": ("public", "Halton District School Board", ["HDSB", "Halton District School Board"]),
 "B66141": ("public", "Hamilton-Wentworth District School Board", ["HWDSB", "Hamilton-Wentworth District School Board"]),
 "B66222": ("public", "Hastings & Prince Edward District School Board", ["HPEDSB", "Hastings Prince Edward", "Hastings & Prince Edward"]),
 "B66079": ("public", "Kawartha Pine Ridge District School Board", ["KPRDSB", "Kawartha Pine Ridge"]),
 "B28045": ("public", "Keewatin-Patricia District School Board", ["KPDSB", "Keewatin"]),
 "B28061": ("public", "Lakehead District School Board", ["Lakehead"]),
 "B66036": ("public", "Lambton Kent District School Board", ["LKDSB", "Lambton Kent"]),
 "B66206": ("public", "Limestone District School Board", ["Limestone"]),
 "B28037": ("public", "Near North District School Board", ["NNDSB", "Near North"]),
 "B66184": ("public", "Ottawa-Carleton District School Board", ["OCDSB", "Ottawa-Carleton District School Board"]),
 "B66125": ("public", "Peel District School Board", ["PDSB", "Peel District School Board"]),
 "B28029": ("public", "Rainbow District School Board", ["RDSB", "Rainbow"]),
 "B28053": ("public", "Rainy River District School Board", ["RRDSB", "Rainy River"]),
 "B66214": ("public", "Renfrew County District School Board", ["RCDSB", "Renfrew County District School Board"]),
 "B66109": ("public", "Simcoe County District School Board", ["Simcoe County District School Board"]),
 "B28070": ("public", "Superior-Greenstone District School Board", ["SGDSB", "Superior-Greenstone", "Superior Greenstone"]),
 "B66044": ("public", "Thames Valley District School Board", ["TVDSB", "Thames Valley"]),
 "B66052": ("public", "Toronto District School Board", ["TDSB", "Toronto District School Board"]),
 "B66087": ("public", "Trillium Lakelands District School Board", ["TLDSB", "Trillium Lakelands", "Trillium District"]),
 "B66192": ("public", "Upper Canada District School Board", ["UCDSB", "Upper Canada"]),
 "B66117": ("public", "Upper Grand District School Board", ["UGDSB", "Upper Grand"]),
 "B66176": ("public", "Waterloo Region District School Board", ["WRDSB", "Waterloo Region District School Board"]),
 "B66095": ("public", "York Region District School Board", ["YRDSB", "York Region District School Board"]),

 # ---- English-language Catholic (29) ----
 "B67202": ("catholic", "Algonquin and Lakeshore Catholic District School Board", ["ALCDSB", "Algonquin and Lakeshore"]),
 "B67164": ("catholic", "Brant Haldimand Norfolk Catholic District School Board", ["BHNCDSB", "Brant Haldimand Norfolk"]),
 "B67008": ("catholic", "Bruce-Grey Catholic District School Board", ["BGCDSB", "Bruce-Grey Catholic", "Bruce Grey Catholic"]),
 "B67172": ("catholic", "Catholic District School Board of Eastern Ontario", ["CDSBEO", "Catholic District School Board of Eastern Ontario"]),
 "B67083": ("catholic", "Dufferin-Peel Catholic District School Board", ["DPCDSB", "Dufferin-Peel Catholic", "Dufferin Peel Catholic"]),
 "B67105": ("catholic", "Durham Catholic District School Board", ["DCDSB", "Durham Catholic"]),
 "B67113": ("catholic", "Halton Catholic District School Board", ["HCDSB", "Halton Catholic"]),
 "B67121": ("catholic", "Hamilton-Wentworth Catholic District School Board", ["HWCDSB", "Hamilton-Wentworth Catholic"]),
 "B67016": ("catholic", "Huron Perth Catholic District School Board", ["HPCDSB", "Huron Perth Catholic", "Huron-Perth Catholic"]),
 "B29025": ("catholic", "Huron-Superior Catholic District School Board", ["HSCDSB", "Huron-Superior Catholic", "Huron Superior Catholic"]),
 "B29050": ("catholic", "Kenora Catholic District School Board", ["KCDSB", "Kenora Catholic"]),
 "B67032": ("catholic", "London District Catholic School Board", ["LDCSB", "London District Catholic"]),
 "B67156": ("catholic", "Niagara Catholic District School Board", ["NCDSB", "Niagara Catholic"]),
 "B29017": ("catholic", "Nipissing-Parry Sound Catholic District School Board", ["NPSCDSB", "Nipissing-Parry Sound", "Nipissing Parry Sound"]),
 "B29009": ("catholic", "Northeastern Catholic District School Board", ["NECDSB", "Northeastern Catholic"]),
 "B29041": ("catholic", "Northwest Catholic District School Board", ["NWCDSB", "Northwest Catholic"]),
 "B67180": ("catholic", "Ottawa Catholic School Board", ["OCSB", "Ottawa Catholic School Board"]),
 "B67067": ("catholic", "Peterborough Victoria Northumberland and Clarington Catholic District School Board",
            ["PVNCCDSB", "PVNC", "Peterborough Victoria Northumberland"]),
 "B67199": ("catholic", "Renfrew County Catholic District School Board", ["RCCDSB", "Renfrew County Catholic"]),
 "B67091": ("catholic", "Simcoe Muskoka Catholic District School Board", ["SMCDSB", "Simcoe Muskoka Catholic"]),
 "B67040": ("catholic", "St Clair Catholic District School Board", ["SCCDSB", "St. Clair Catholic", "St Clair Catholic"]),
 "B29033": ("catholic", "Sudbury Catholic District School Board", ["Sudbury Catholic"]),
 "B29076": ("catholic", "Superior North Catholic District School Board", ["SNCDSB", "Superior North Catholic"]),
 "B29068": ("catholic", "Thunder Bay Catholic District School Board", ["TBCDSB", "Thunder Bay Catholic"]),
 "B67059": ("catholic", "Toronto Catholic District School Board", ["TCDSB", "Toronto Catholic"]),
 "B67148": ("catholic", "Waterloo Catholic District School Board", ["Waterloo Catholic"]),
 "B67130": ("catholic", "Wellington Catholic District School Board", ["Wellington Catholic"]),
 "B67024": ("catholic", "Windsor-Essex Catholic District School Board", ["WECDSB", "Windsor-Essex Catholic", "Windsor Essex Catholic"]),
 "B67075": ("catholic", "York Catholic District School Board", ["YCDSB", "York Catholic"]),
}

# Acronyms two boards both use. Never assigned; see the module docstring.
AMBIGUOUS = {
    "SCDSB": ("B66109", "B29033"),   # Simcoe County DSB / Sudbury Catholic DSB
    "WCDSB": ("B67148", "B67130"),   # Waterloo Catholic / Wellington Catholic
}

# French-language boards, and the French half of a bilingual label. Matched only to drop
# the race deliberately rather than let it fall through to the generic system test.
FRENCH = re.compile(
    r"conseil scolaire|viamonde|monavenir|mon avenir|providence|franco-nord|aurores|"
    r"grandes rivi|nouvel-ontario|centre-est|est ontarien|grand nord|nord-est|"
    r"\bCEPEO\b|\bCSDCEO\b|\bCSPGNO\b|\bCSCFN\b|french", re.I)

_TRUSTEE = re.compile(r"trustee|school board|conseiller|membre du conseil", re.I)
# A generic label names the system but no board.
_CATHOLIC_SYSTEM = re.compile(r"english\s*[- ]?\s*(separate|catholic)|"
                              r"(separate|catholic)\s+school\s+(board\s+)?trustee|"
                              r"trustee\s+english\s+(separate|catholic)", re.I)
_PUBLIC_SYSTEM = re.compile(r"english\s*[- ]?\s*public|"
                            r"public\s+school\s+(board\s+)?trustee|"
                            r"trustee\s+english\s+public", re.I)

_KEYS = []
for _num, (_sys, _name, _keys) in BOARDS.items():
    for _k in _keys:
        if _k in AMBIGUOUS:
            continue
        # a bare acronym must stand alone; a name fragment may appear anywhere
        _pat = (r"\b%s\b" % re.escape(_k)) if (_k.isupper() and len(_k) <= 8) else re.escape(_k)
        _KEYS.append((_num, _sys, _k, re.compile(_pat, re.I)))
# longest key first, so a full name beats a short acronym that happens to be a substring
_KEYS.sort(key=lambda t: -len(t[2]))

_AMB = [(a, re.compile(r"\b%s\b" % a, re.I)) for a in AMBIGUOUS]


def classify(office):
    """Return (board_number, system, reason).

    board_number is one of:
      "B66125"              a board was identified outright
      "UNRESOLVED-public"   an English public race whose board follows from the municipality
      "UNRESOLVED-catholic" ditto, Catholic
      "AMBIGUOUS-SCDSB"     an acronym two boards share; needs the municipality
      None                  not an in-scope race (French, or not a trustee race at all)
    system is "public", "catholic" or None.
    """
    if not _TRUSTEE.search(office):
        return None, None, "not-a-trustee-race"
    if FRENCH.search(office):
        return None, None, "french-language-board"
    for num, system, key, rx in _KEYS:
        if rx.search(office):
            return num, system, f"matched:{key}"
    for acr, rx in _AMB:
        if rx.search(office):
            return f"AMBIGUOUS-{acr}", None, f"ambiguous-acronym:{acr}"
    # Catholic first: "English Separate" also contains "School Trustee".
    if _CATHOLIC_SYSTEM.search(office):
        return "UNRESOLVED-catholic", "catholic", "generic-catholic-label"
    if _PUBLIC_SYSTEM.search(office):
        return "UNRESOLVED-public", "public", "generic-public-label"
    return None, None, "unclassified"
