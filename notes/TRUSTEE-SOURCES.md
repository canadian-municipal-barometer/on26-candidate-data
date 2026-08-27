# School board trustee data: sources and method

Companion to the trustee files in this repo, in the style of `notes/SOURCES.md`. Collected
August 2026 for the **2026 Ontario municipal and school board election** (voting day Monday,
October 26, 2026; nominations closed Friday, August 21, 2026).

Scope: the **60 English-language district school boards** — 31 public, 29 Catholic. The 4
French-language public, 8 French-language Catholic, 4 elected school authorities and 8
appointed hospital/provincial authorities are out of scope by decision.

Purpose: a **sampling frame** for the CMB's 2026 School Board Trustee Candidate Survey
(`school-board-candidate-survey/ON School board candidate survey - August25.docx`). Not a
Qualtrics respondent list — nothing here is served to respondents.

## The thing to understand before reading any of it

**A municipality is not a school board district.** A trustee contest is a **(board × zone)**
pair, drawn by each board under [O. Reg. 412/00](https://www.ontario.ca/laws/regulation/000412/v2).
Municipalities only *administer*: the clerk runs the election and publishes the list. Zones
break the municipal frame in every direction, and all four cases occur in this data:

| Pattern | Case |
|---|---|
| One zone spans several whole municipalities | YRDSB Trustee Area 1 = Georgina + East Gwillimbury; CDSBEO zone = South Glengarry + North Glengarry |
| One municipality split across several zones | Guelph → 3 UGDSB zones; London → 3 TVDSB zones; Toronto → 12 TDSB wards |
| Zone mixes partial and whole municipalities | UGDSB = "Ward 6, Puslinch"; YRDSB TA 4 = Vaughan Ward 1 + King |
| One municipality in **two boards of one system** | Georgian Bay Township elects a Near North trustee *or* a Trillium Lakelands one |

That last row is why the partition claim has to be stated carefully: the 31 public boards
partition Ontario's **territory**, not its municipalities. A municipality has *at least* one
board of each system, not exactly one.

**Consequence for collection.** The same contest is published by every clerk in its zone,
with different fields on each — Guelph prints the zone label `Ward 6, Puslinch` and no
vote-for count; Puslinch prints "vote for no more than one" and no zone label; both list the
same two candidates. So candidates are keyed on **(board, folded name)** and merged across
sources, never counted per municipality. 31 candidates in the current frame were seen in more
than one municipality and merged.

## 2026-specific context

- **Bill 101** (*Putting Student Achievement First Act, 2026*) caps trustees at **12 per
  board**. TDSB was the only board over the cap and was redrawn from 22 wards to 12; its new
  map was released late April 2026. Every other board's standing distribution carries forward.
  Any 2022 zone document is therefore safe to read *except* TDSB's.
- **Eight boards are under provincial supervision**, with the elected trustees' role
  effectively suspended (Catholic trustees keep denominational matters). Five are public —
  TDSB, OCDSB, Thames Valley, Near North, Peel — and three Catholic — Toronto Catholic,
  Dufferin-Peel Catholic, York Catholic. Carried as `supervised` in `data/boards/boards.csv`.
  Source: Global News, ["Fewer people running for trustee in some of Ontario's supervised
  school boards"](https://globalnews.ca/news/12025167/ontario-school-trustee-elections/),
  2026-08-18. This is a study covariate, not a footnote: the survey's `DIVISION` battery and
  its "capped at 12" attitude item are about exactly this.

## Sources, in the order they were tried

**1. Ministry of Education board list** — `data/raw/school-board-contact-list-2026-08-19.csv`,
vendored from [data.ontario.ca](https://data.ontario.ca/dataset/school-board-and-school-authority-contact-information).
The authoritative universe: 31/29/4/8 by type and language, asserted by
`scripts/build-boards-csv.py`. Encoded **cp1252**, and it carries a duplicate row (Grandview
School Authority) that the build catches.

**2. VoterView** — 41 of the 414 ballot-running municipalities use this election platform,
which serves an undocumented endpoint at
`ovs.voterview.ca/candidateList/candidatedetails?countyMun=NNNN`. The `countyMun` code is not
published anywhere but is derivable from the census subdivision: CD number + last two digits
of CSD number (Mississauga 3521005 → 2105). Verified collision-free across all 414.
Structured and rich where populated — zone label, acclamation flag, email, phone, socials.
**Some instances are stale**: Ajax's still said "No candidates have yet been nominated" six
days after the deadline while its own website carried the list, so an empty contest from this
source is never read as a zero.

**3. Toronto's own JSON feed** — `toronto.ca/data/elections/candidate_list/trusteeCandidates_2026.json`.
Toronto is not on VoterView and its page renders entirely in JavaScript, but it is a thin
shell over this file, which is a better source than the page: names arrive already split,
with email, phone, socials and a status field. 108 candidates over 24 zones.

**4. Municipal websites** — `scripts/crawl-municipal-elections.py` walks from each
municipality's official site to its candidate list. URLs come from
`notes/municipal-websites.csv`, built from MMAH's
[List of municipalities](https://data.ontario.ca/dataset/municipalities), which hides the
official URL inside an HTML anchor. Of 373 crawled: 217 found a list, 131 found none, 22
unreachable, 3 have no website (Brethour, Gauthier and Thornloe, all in Timiskaming).

**Both municipality files are mis-encoded, in different ways**, and both are repaired in
`scripts/build-municipal-websites.py`. The study's master list *mixes* encodings — raw
latin-1 bytes (187 × 0xE9) alongside UTF-8 sequences (200 × 0xC3 0xA9) — so no single codec
reads it. MMAH's file is *double-encoded*: valid UTF-8 spelling out a latin-1 misreading, so
a correct read still yields "Mattice-Val CÃ´tÃ©". Both are worth fixing at the source. Once
repaired the two files agree exactly: **444 municipalities, of which 414 run a ballot** and 30
are upper-tier counties and regions that do not.

**5. Greater Sudbury** publishes a PDF (`List-of-Certified-Candidates.pdf`), readable with
`pdftotext -layout`. Rainbow DSB over 6 areas and Sudbury Catholic over 6 zones, with
ACCLAIMED markers. Not yet folded into the frame.

## What is inferred rather than read

`notes/board-jurisdictions.csv` says which board serves which municipality. It has to exist
because many clerks label a race only by system — "English Public School Trustee" names no
board — and such a contest cannot be attributed without it.

- **300 rows are read** from a source that named the board outright, 178 of them corroborated
  by two or more independent sources.
- **331 rows are inferred from county consensus**: where every placed municipality of a county
  agrees on one board of a system, that board is inferred for the county's remaining
  municipalities. It requires unanimity and at least two backers, never overrides direct
  evidence, and is stamped `county-inference` so it can be filtered out in one step. **It will
  be wrong somewhere** — Georgian Bay is proof that boards cross county lines. Treat an
  inferred row as a lead to verify.
- **2 rows are hand overrides** in `notes/board-jurisdiction-overrides.csv`, each with a
  reason and a source. Hamilton is the case: its clerk never names a board anywhere.

## Known gaps

- **Ottawa** — OCDSB and Ottawa Catholic have no candidates collected. The site is behind
  Incapsula (blocks scripted fetches) and fragments its list across per-office subpages that
  could not be located; the trustee subpage 404s under every guessed name. Needs a hand read.
- **15 of 60 boards have no candidates yet**, concentrated in the north and east — most are
  municipalities the crawl could not read, not municipalities without contests.
- **Contact coverage is 41%**, and it is the number that decides whether the survey can be
  fielded as designed. It varies enormously by source: Hamilton 97%, the VoterView sweep 28%,
  Toronto 33%. Where a clerk publishes contact at all, extraction gets most of it; where the
  clerk publishes none, nothing here can conjure it. The remaining lever is the clerk's own
  office — nomination papers (Form 1) carry contact details — which is a records request, not
  a scrape.
- `data/raw/trustees/municipal-trustee-sections.json` is a **work queue, not data**: the
  trustee section of every crawled page, with a confidence flag. 122 pages read high, 108 low.
  It is deliberately excluded from the frame.
