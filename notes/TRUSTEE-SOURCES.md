# School board trustee data: sources and method

Companion to the trustee files in this repo, in the style of `notes/SOURCES.md`. Collected
August 2026, re-collected in full on 2026-09-02, and **re-collected again on 2026-09-04**
for the **2026 Ontario municipal and school board election** (voting day Monday, October 26,
2026; nominations closed Friday, August 21, 2026, reopened by s. 33(5) of the *Municipal
Elections Act* until 2pm Wednesday August 26 for any office that drew fewer candidates than
seats).

Every number below is from the 2026-09-04 run. What changed against 2026-09-02 is set out
under **What the re-run changed**; the short version is that the frame went from 667
candidates over 45 boards to **868 over all 60**, and that most of what left was never a
trustee candidate.

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
| One municipality split across several zones | Guelph → 3 UGDSB zones; London → 3 TVDSB zones; Ottawa → 12 OCDSB zones |
| Zone mixes partial and whole municipalities | UGDSB = "Ward 6, Puslinch"; YRDSB TA 4 = Vaughan Ward 1 + King |
| One municipality in **two boards of one system** | Georgian Bay Township elects a Near North trustee *or* a Trillium Lakelands one |

That last row is why the partition claim has to be stated carefully: the 31 public boards
partition Ontario's **territory**, not its municipalities. A municipality has *at least* one
board of each system, not exactly one. It is now attested twice over — Georgian Bay's ballot
says so, and so does the ministry's school list, which puts a Near North school at Mactier
and a Trillium Lakelands one at Honey Harbour, both inside the township.

**Consequence for collection.** The same contest is published by every clerk in its zone,
with different fields on each — Guelph prints the zone label `Ward 6, Puslinch` and no
vote-for count; Puslinch prints "vote for no more than one" and no zone label; both list the
same two candidates. So candidates are keyed on **(board, folded name)** and merged across
sources, never counted per municipality. 79 candidates in the current frame were seen in
more than one municipality and merged.

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

**2. Ministry of Education school list** — `data/raw/sif-school-information-2024-2025.xlsx`,
vendored from data.ontario.ca's ["School information and student
demographics"](https://data.ontario.ca/dataset/school-information-and-student-demographics)
(the "Preliminary 2024-2025" resource, published 2026-08-18). New in this run, and the
single most useful thing added: every school in Ontario with its board **and its
municipality**, keyed on the same `B*` board numbers this repo already uses.
`scripts/build-board-municipalities.py` turns it into `notes/board-municipalities.csv` —
526 (municipality, board) pairs covering 322 of the 414 ballot-running municipalities and
**all 60 boards**. See **What is inferred rather than read**, which it largely replaced.

**3. VoterView** — 45 of the 414 ballot-running municipalities use this election platform,
which serves an undocumented endpoint at
`ovs.voterview.ca/candidateList/candidatedetails?countyMun=NNNN`. The `countyMun` code is not
published anywhere but is derivable from the census subdivision: CD number + last two digits
of CSD number (Mississauga 3521005 → 2105). Verified collision-free across all 414.
Structured and rich where populated — zone label, acclamation flag, email, phone, socials.
142 contests, 421 candidates. **Some instances are stale**: Ajax's still said "No candidates
have yet been nominated" after the deadline while its own website carried the list, so an
empty contest from this source is never read as a zero.

Membership is detected by the **rendered** `<button id="expandAllCandidateList"`, not by the
bare id: the page's jQuery ships the handler naming it to every municipality, so an id test
calls all 414 members. And the clerks' own test entries are refused by name — a record with
TEST as a whole word. That rule caught 3 records on 2026-08-27 and **7** now, including two
shapes it had not seen before (`FRANKI-TEST IKEMAN`, `TEST CARMICHAEL`), which is the
argument for keeping the refusals printed rather than silent. A late nomination date is
deliberately *not* used as that test: s. 33(5) reopens nominations for under-subscribed
offices, so the two trustees nominated on 24 and 26 August are ordinary candidates.

**4. Toronto's own JSON feed** — `toronto.ca/data/elections/candidate_list/trusteeCandidates_2026.json`.
Toronto is not on VoterView and its page renders entirely in JavaScript, but it is a thin
shell over this file, which is a better source than the page: names arrive already split,
with email, phone, socials and a status field. 108 candidates over 24 zones.

**5. Municipal websites** — `scripts/crawl-municipal-elections.py` walks from each
municipality's official site to its candidate list. Of 369 crawled (the other 45 are on
VoterView): **227 found a list** (213 by walking, 14 from a seed), 134 found none, 5
unreachable, 3 have no website. 154 of the pages found name at least one board.

Two things make this better than the 2026-09-02 run, which found 214 and reached 142:

- **Seeds.** For 17 municipalities this repo already knew the candidate-list URL, because
  `data/raw/by-municipality/` cites it as the source of that city's *council* candidates.
  `notes/municipal-election-page-seeds.csv` feeds those to the crawl, which tries them first
  and keeps them only if they pass the same test as any other page. Re-deriving them by
  scoring links was work the crawl could lose: it had stopped at Kingston's press release
  rather than its candidate list, and found nothing at all for Greater Sudbury,
  Chatham-Kent and New Tecumseth.
- **Repaired URLs.** See below.

**MMAH's URL column is out of date, not just mis-encoded.** 17 of the 414 municipalities
were recorded at a host that no longer resolves, having moved domain since MMAH last
refreshed the column, and a dead URL costs the crawl the whole municipality. Each is
repaired in `notes/municipal-website-overrides.csv` with the live host, the reason, and the
date it was verified; `scripts/build-municipal-websites.py` applies them, and treats
`old_website` as a precondition so a row that no longer describes MMAH's file is reported
rather than applied. Unreachable municipalities fell from 22 to 5. This is the change that
brought Haldimand County's trustees back — its recorded `haldimandcounty.on.ca` does not
resolve while `haldimandcounty.ca`, which this repo's own council data already cites, does.

The eight still unread are Beckwith, Lanark Highlands, Merrickville-Wolford and Nipigon
(which answer by hand, so those are timeouts), Hilton Beach (no live site found under any
guessed domain), and Brethour, Gauthier and Thornloe, which MMAH records as having no
website at all.

**Both municipality files are mis-encoded, in different ways**, and both are repaired in
`scripts/build-municipal-websites.py`. The study's master list *mixes* encodings — raw
latin-1 bytes alongside UTF-8 sequences — so no single codec reads it. MMAH's file is
*double-encoded*: valid UTF-8 spelling out a latin-1 misreading, so a correct read still
yields "Mattice-Val CÃ´tÃ©". Both are worth fixing at the source. Once repaired the two
files agree exactly: **444 municipalities, of which 414 run a ballot**.

**6. Hand-collected lists** — `data/raw/trustees/by-zone/`, read by
`scripts/harvest-by-zone.py`. The directory existed and was empty; three municipalities now
live in it, 36 contests and 73 candidates, because no scraper can reach them:

- **Ottawa** (49 candidates, 83% reachable). ottawa.ca sits behind Incapsula, which answers
  any scripted fetch with a JavaScript challenge — curl gets 1.1KB of challenge script
  whatever headers it sends — so the crawl records Ottawa as no-list-found. Read in a real
  browser instead. The trustee list is also not a named subpage but a query parameter,
  `?page=3044842`, which is why every guessed path 404'd. OCDSB over 12 zones and Ottawa
  Catholic over 10, the latter with 5 acclamations stated in each table's caption.
- **Greater Sudbury** (15 candidates). Publishes only a PDF, linked from a page that carries
  no names at all; the crawl excludes `.pdf` hrefs by design and so can never reach it. Read
  with `pdftotext -layout`, by eye rather than by parser: the layout wraps each office label
  across two lines and lifts ACCLAIMED into the gap between them. Rainbow DSB over 6 areas
  and Sudbury Catholic over 6 zones, 10 of the 15 acclaimed.
- **Kenora** (9 candidates). Publishes headings and plain paragraphs with no table anywhere,
  so the table reader finds nothing on a page the crawl reaches correctly.

`harvest-by-zone.py` is a thin translator and the checks are the point: a hand-written file
is the one input with no upstream format to keep it honest, so it refuses an unknown board,
a system that disagrees with the board, a duplicate name within a contest, a one-word name,
and any name still carrying a WITHDRAWN or ACCLAIMED marker.

## Reading a clerk's page: what `harvest-accordion.py` learned this run

The commonest municipal layout is a label followed by a table of candidates, and the reader
for it went from 245 candidates over 44 municipalities to **372 over 78**. Almost none of
that came from finding new pages; it came from six things the reader was getting wrong. Each
is worth recording because each was silently producing *wrong* data, not merely missing it.

- **A `<caption>` is a child of its table**, so it opens after the table does, and a reader
  pairing each table with the nearest label that *ends before* it starts gave every caption
  to the NEXT table. Every label on such a page was shifted by one. Haldimand County's Grand
  Erie trustees were filed under a "Ward 7 candidates" heading and lost; West Nipissing's
  five Near North candidates were filed under **Nipissing-Parry Sound Catholic**; two of
  Innisfil's *French* candidates arrived under Simcoe Muskoka Catholic. Captions are correct,
  ordinary HTML; the reader was wrong.
- **The section heading was overriding the table's own label.** It is sticky — it applies to
  every table below it — so on a page that lists the French boards above the English ones,
  prefixing it made `classify()` return french-language-board for contests that were never
  French. The label is now classified on its own first, and the heading consulted only if
  that says nothing.
- **The label can be inside the table**, in the first cell of its header row (Terrace Bay,
  Manitouwadge, Marathon) or in a lone spanning cell above the names (Dryden). Those pages
  have no caption, no button and no heading, so a reader that only looks *above* the table
  attributes the contest to the last unrelated thing on the page.
- **The contest can be a column** rather than a label — `Office | Name of Candidate |
  Qualifying Address`, one row per candidate, council and trustee races sharing one table.
  Six crawled pages are this shape and none of them yielded anything before. Reading
  `cells[0]` as the name is why: `cells[0]` is the office.
- **A table can change contest halfway down.** Stone Mills publishes all four of its trustee
  contests in one table, each introduced by a row holding a single spanning cell. Taking the
  first as the whole table's label put a Catholic candidate under a public board and two
  French-board candidates into a frame that excludes French boards.
- **A results table is not a candidate list**, and Brockville, East Garafraxa and Killarney
  each publish both on one page. Killarney's Alex Cimino and Claire Morrison polled 35 and 68
  votes in 2022 and were arriving beside its actual 2026 trustees. The test is the data and
  not the header — East Garafraxa heads the column "Votes" and Killarney "Number of Votes",
  and a candidate list published before voting day could carry an empty one — so a table is
  refused only when that column actually holds a count.

Three smaller rules came out of the same reading: acclamation is stated in front of the name
as often as after it ("ACCLAIMED Brandy Rafeek") and sometimes only in the column header
("Name of Acclaimed Candidate") or on the contest ("...English Public - ACCLAIMED"); a name
split across `LAST NAME` and `FIRST NAME` columns must be read from both, or Brockville's
Theresa Lalonde Pankow arrives as a bare surname; and a footnote saying which clerk certified
a cross-boundary trustee ("Marnie Van Esbroeck *Certified by South Huron Clerk") is not part
of the name, and left on it becomes a second candidate.

**Two fixes belong to `trustee_boards.py` rather than the reader**, and both were refusing
whole contests:

- `classify()` tested for the word "trustee" or "school board" *before* testing for a French
  board. A French board's own name contains neither — "Conseil Scolaire Catholique
  Providence" — so it came back as `not-a-trustee-race`. Both answers refuse the race, but
  only one says why, and the reader needs the difference to stop at a French heading instead
  of letting the English heading above it stand. Ingersoll's French separate trustee reached
  the 2026-09-02 frame as a London District Catholic one for want of this.
- "English **Language** Public" and "English Language Catholic" were not recognised as system
  labels at all. A label that classifies to nothing falls back to the section heading, which
  is how Port Colborne's Catholic contest was attributed to the District School Board of
  Niagara — the public board named further up its page.

## What is inferred rather than read

`notes/board-jurisdictions.csv` says which board serves which municipality. It has to exist
because many clerks label a race only by system — "English Public School Trustee" names no
board — and such a contest cannot be attributed without it.

The ministry school list changed the shape of this file. It is **positive evidence, not
inference**: a board that operates a school in a municipality serves that municipality, and
that is published by the same ministry that defines the boards.

| | 2026-09-02 | 2026-09-04 |
|---|---|---|
| rows | 621 | **781** |
| read from a source | 303 | **596** |
| inferred from county | 318 | **185** |
| public municipalities placed | 358 | **404** of 414 |
| Catholic municipalities placed | 299 | **373** of 414 |
| boards reached | 58 | **60** of 60 |

**Temagami is the case for having done it.** Its public row was inferred from its county on
2026-08-27, lost on 2026-09-02 when the evidence set moved, and the obvious hand fix is Near
North — Temagami is in Nipissing District and Near North covers Nipissing. That is wrong.
Temagami Public School belongs to **District School Board Ontario North East**, a board this
study had no candidates for at all. Every hand-written override is a guess of that shape
waiting to happen, which is why the 54 unresolved candidates of the 2026-09-02 run were
fixed with a corpus rather than with fourteen override rows.

**County inference survives, and still has to**, for the 92 municipalities with no school of
their own: a board that runs no school in a township can still have it in its jurisdiction.
185 rows are still `county-inference` and are still leads rather than readings.

**The ministry's `Municipality` column has errors in it**, and they are wrong values rather
than encoding problems — St James Major, in Sharbot Lake, is filed under "Essex, County of";
four Kawartha Pine Ridge schools around Cobourg are filed under "Hamilton, City of" when they
are in Hamilton *Township*. Left alone they invent jurisdictions. Each pair is therefore
screened on one postal letter against the rest of its county, which drops 11 pairs and is
documented at length in `scripts/build-board-municipalities.py`. The screen costs one true
pair — South Algonquin's Renfrew County DSB school is K0J because the township sits on the
Renfrew border while the rest of Nipissing is P — and that municipality is placed by the
crawl anyway.

**Hamilton needed a rule of its own.** It is the only bare name two ballot-running
municipalities share, and the ministry's status word cannot break the tie because it uses
both values for the city: all 136 rows reading "Hamilton, Township of" are the city, and the
28 reading "Hamilton, City of" are 24 city schools and 4 township ones. The postal letter
decides it. The count of shared names is asserted, so a second one appearing in a future
release stops the run rather than being resolved by a rule written for Hamilton.

**2 rows are hand overrides** in `notes/board-jurisdiction-overrides.csv`, both Hamilton's,
whose clerk never names a board anywhere. The school list now corroborates both
independently.

## What the re-run changed

| | 2026-08-27 | 2026-09-02 | **2026-09-04** |
|---|---|---|---|
| candidates | 707 | 667 | **868** |
| boards represented | 45 | 45 | **60 of 60** |
| reachable by ≥1 channel | 296 (42%) | 280 (41%) | **379 (43%)** |
| with an email | 256 | 236 | **331 (38%)** |
| acclaimed | 8 | 30 | **70** |
| dropped, board unresolved | — | 54 | **0** |

At the **contest** grain (`notes/trustee-zones.csv`) that is 333 distinct (board × zone)
contests, 30 duplicate publications merged away, and — for the first time — **no contest
whose board is unknown**. 276 were named by a clerk outright, 12 identified by their
candidate set matching a contest that was, and 45 resolved from the jurisdiction crosswalk.
That last step is what `build-trustee-frame.py` had always done and `build-trustee-zones.py`
had not, which is why the two files used to disagree about the same data.

Against the last committed frame (2026-08-27), 244 candidates arrived and 83 left. Of those
83, **14 are the same person under a corrected board** and only 69 are gone — and almost all
of the 69 were never trustee candidates:

- **Georgian Bluffs contributed 13 rows and should have contributed 2.** Its mayor, deputy
  mayor and nine councillors were reaching the frame as Bluewater DSB trustees. It now yields
  Leslie Patrick Medve (Bluewater) and Lucie Desbiens (Bruce-Grey Catholic), both acclaimed,
  both with an email — which is the entire correct answer for that page.
- **Arnprior contributed 13 and should have contributed none.** Its page is general election
  information and carries no candidate list at all.
- **Port Colborne contributed 9 and should have contributed 2.** Mark Bagu, in the frame as a
  District School Board of Niagara trustee, is a Ward 1 Councillor. Danny DiLorenzo, in the
  frame under the same public board, is a Niagara *Catholic* trustee. Both are now right.
- **East Garafraxa contributed 7 from the 2022 election.** Its page publishes 2022 results and
  2022 nomination dates; the vote counts are still on it.
- **Five French-board candidates left**, having been filed under English boards: David Paradis
  (Conseil scolaire Viamonde) under *two* English Catholic boards, Eric Lapointe and Rachael
  Golem, Geneviève Grenier and Patrick O'Neil, and Joseph-Guy Bourbeau.
- **Labels that are not people left** — "Avon Maitland District School Board" from Stratford,
  "English Separate: Durham Catholic" from Scugog, "Mayor and, by virtue of office, Regional
  Councillor" from Port Colborne.

The acclamation count going 8 → 30 → 70 is the same story from the other side. Markers were
being left inside the name, which both put "- ACCLAIMED" in the salutation of a survey
invitation and read the flag as 0 for someone who was acclaimed; 2026-09-02 fixed the
trailing form and this run fixed the leading form, the header form and the office form.

**All 15 boards that had no candidates now have some.** Twelve came from work described
above — Ottawa's two, Greater Sudbury's two and Kenora's Catholic board by hand; Lakehead,
Thunder Bay Catholic and Limestone from seeded crawls of Thunder Bay and Kingston;
Superior-Greenstone and Superior North Catholic from Terrace Bay once the header-row label
was read; Keewatin-Patricia and Northwest Catholic from Dryden's spanning-cell labels;
Northeastern Catholic from Temiskaming Shores and Rainy River DSB from Emo once the
office-column layout was read; and DSB Ontario North East from Temagami, once the school
list said which board Temagami is in.

## Known gaps

- **Reachability is 43%** (379 of 868 by email, phone or website; 331 by email), and it is
  the number that decides whether the survey can be fielded as designed. It varies by source:
  hand-collected 56%, the municipal-page reader 53%, Toronto 41%, the VoterView sweep 36%.
  Where a clerk publishes contact at all, extraction gets most of it; where the clerk
  publishes none, nothing here can conjure it. The remaining lever is the clerk's own office
  — nomination papers (Form 1) carry contact details — which is a records request, not a
  scrape.
- **Coverage is uneven, and the thin boards are thin because their municipalities are.**
  Rainy River DSB, Superior-Greenstone and Northeastern Catholic have one candidate each;
  they are represented rather than collected. The municipalities that would fill them —
  Fort Frances, Timmins, Kirkland Lake, Red Lake, Atikokan — are all `no-list-found`, and
  each needs a hand read of the kind Kenora and Greater Sudbury got.
- **134 crawled pages found no list.** Some genuinely have none yet; some put it behind a
  PDF, a JavaScript shell, or a link the scoring does not reach. This is the largest single
  pool of unread municipalities and the obvious next thing to work through, using
  `data/raw/trustees/municipal-trustee-sections.json` as the queue.
- **Uxbridge published two public trustee candidates on 2026-08-27 and four entirely
  different ones on 2026-09-02**, all with 2026 nomination dates. The later read is kept, but
  the swap still wants a hand check.
- **Oshawa's Kristine Dandavino** was in the 2026-08-27 frame and is not on Oshawa's
  VoterView list, which carries three names for Durham Catholic. Still worth a hand check
  rather than an assumption.
- **185 jurisdiction rows are still county inferences** and will be wrong somewhere. They are
  stamped so they can be filtered out in one step.
- **Four municipalities are served by two boards of one system** in the school list — Georgian
  Bay, Neebing, Kenora and Quinte West. Georgian Bay and Quinte West are corroborated. Kenora's
  second row is a mislabel the postal screen cannot catch (its lone Rainy River school is
  Nestor Falls Public School, in Sioux Narrows-Nestor Falls) and is recorded as such in
  Kenora's by-zone file; Neebing's is unverified.
- `data/raw/trustees/municipal-trustee-sections.json` is a **work queue, not data**: the
  trustee section of every crawled page, with a confidence flag. Of 227 pages, 121 read high,
  14 medium and 92 low. It is deliberately excluded from the frame.
