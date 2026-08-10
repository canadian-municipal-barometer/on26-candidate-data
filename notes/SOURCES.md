# Ballot structure notes and sources

Companion to `election-type-ward-type.csv`, `council-races.csv`, and
`classification-overrides.csv`, all alongside this file. Researched August 2026 for the
**2026 Ontario municipal election cycle** (voting day Monday, October 26, 2026). Where 2026
material was not yet published, the 2022 structure is used and flagged as such below.

## Where these files live

Everything is in the **`on26-candidate-data`** repo: these notes in `notes/`, and the
script that reads and writes them at `R/get-municipal-data.R`.

- **Usage:** `Rscript R/get-municipal-data.R`. Like `R/parse-js.R`, it locates the repo
  root from its own path, so it runs from any working directory.
- `council-races.csv` and `classification-overrides.csv` are hand-maintained and never
  generated. `election-type-ward-type.csv` **is** generated — do not hand-edit it; every
  run overwrites it.
- The script reads one file from outside the repo: the master municipality list at
  `CMB Data/auxiliary-data/Master Municipality List/cmb_muns.csv`, by absolute path. It
  also reads the Google Sheet that selects which municipalities are in the study, so it
  needs `googlesheets4` auth.

## Why this file exists

`election-type-ward-type.csv` codes municipalities as SMD / MMD / Mixed / N/A. That coding
does not answer the question the survey needs: **does a voter mark more than one name in a
single contest?** `MMD` turns out to cover two very different ballot experiences:

- **Block vote (plurality-at-large)** — one contest, N seats, voter marks up to N names.
  Guelph's wards each elect two councillors in a single vote-for-2 race.
- **Double-direct / paired-ward** — a ward returns two councillors, but as two *separate
  single-seat offices* (e.g. Regional Councillor and City Councillor). Brampton's 2022
  ballots literally read "Vote For 1". The voter's experience is identical to SMD.

`council-races.csv` records each distinct contest so the two can be told apart.
`block_vote` and `max_votes_max` in the main CSV are **derived** from it by
`get-municipal-data.R`, never typed by hand.

## `ward_type` and `block_vote` measure different things — both are correct

They are orthogonal, and a municipality can be MMD with `block_vote = FALSE`:

- **`ward_type`** is about **district magnitude** — how many council seats a district
  returns.
- **`block_vote`** is about **the ballot** — how many names a voter marks in one contest.

**Brampton is the worked example.** Its ten wards are paired (1&5, 2&6, 3&4, 7&8, 9&10).
Each pairing elects a Regional Councillor *and* a City Councillor, and **both sit on
Brampton City Council** — the regional councillors are city councillors too, which is why
AMO lists the office as regional-and-city. So each district returns two seats: magnitude 2,
correctly coded `MMD`. But they are two separate offices on the ballot, each vote-for-one,
so `block_vote = FALSE`. Council is the mayor plus five regional and five city councillors.

Both facts live in `council-races.csv`. Votes per contest is `max_votes`. District magnitude
is derivable by grouping on `districts` and summing seats:

```r
races |>
  group_by(census_id, districts) |>
  summarise(magnitude = sum(seats_per_district), .groups = "drop")
```

For Brampton that returns 2 for every ward pairing.

A general derived-magnitude-vs-`ward_type` check is *not* implemented: ward and ward-pair
districts overlap (Clarington), magnitude varies within a municipality (Chatham-Kent), and
`Mixed` sometimes means at-large-plus-ward rather than mixed magnitude (Markham, Thunder
Bay). Any such check would fire on all three without a real error. Instead
`get-municipal-data.R` verifies that councillor seats implied by `council-races.csv` equal
`council_size - 1` in the master list, which is unambiguous and catches the same class of
typo. Seven municipalities deviate for known reasons and are listed as documented
exceptions in the script — at-large deputy mayors (Bradford West Gwillimbury, Innisfil),
regional councillors who sit on regional rather than city council (Cambridge, Kitchener,
Waterloo), and stale `council_size` values (Chatham-Kent, Haldimand County).

The same reasoning applies to Milton, Oakville, Oshawa, Pickering, Clarington and Ajax: all
are genuinely multi-member in seats and genuinely vote-for-one on the ballot.

## Scope

`council-races.csv` covers **councillor** offices only. Mayoral races and the separately
elected at-large deputy mayor seats in Bradford West Gwillimbury and Innisfil are excluded:
all are single-seat and would not change `block_vote` for any municipality.

Rows are collapsed across districts that share a structure, so Toronto is one row and
Chatham-Kent is two. `n_districts` says how many districts a row covers.

## Result: 15 of 38 municipalities have at least one multiple-vote race

### Multi-member wards — voter marks N names in their own ward's race

| Municipality | Structure | Votes |
|---|---|---|
| Brantford | 5 wards × 2 councillors | 2 |
| Guelph | 6 wards × 2 councillors | 2 |
| Peterborough | 5 wards × 2 councillors | 2 |
| St. Catharines | 6 wards × 2 city councillors | 2 |
| Chatham-Kent | 8 wards for 2026; Wards 1, 2, 5, 6, 7, 8 elect 2, Wards 3 & 4 elect 1 | 1 or 2 by ward |
| Timmins | Ward 5 elects 4 by plurality block vote; Wards 1–4 elect 1 each | 4 in Ward 5 only |

### At-large block vote

| Municipality | Structure | Votes |
|---|---|---|
| Niagara Falls | 8 councillors, whole council, one contest | 8 |
| Thunder Bay | 5 at-large councillors + 7 single-member wards | 5 |
| Sarnia | two separate at-large contests: 4 City Councillors, 4 City-County Councillors | 4 in each |
| Kitchener | 4 Regional Councillors at-large + 10 wards | 4 |
| Markham | 4 Regional Councillors at-large + 8 wards | 4 |
| Vaughan | 4 Local & Regional Councillors at-large + 5 wards | 4 |
| Cambridge | 2 Regional Councillors at-large + 8 wards | 2 |
| Waterloo | 2 Regional Councillors at-large + 7 wards | 2 |
| Richmond Hill | 2 Regional & Local Councillors at-large + 6 wards | 2 |

No municipality has a multiple-vote race at both levels. St. Catharines did until the
2026 Niagara governance change removed its at-large regional race — see below.

### Niagara abolished its elected regional councillors for 2026

Provincial change, effective **with the October 2026 election**: "the independently elected
Regional Councillors will be eliminated. Regional Council will be made up of the 12 mayors
plus the Regional Chair." Council drops from 31 members to 13.

This removes two races that existed in 2022:

- **St. Catharines** — its 6 at-large Regional Councillors are gone. St. Catharines was
  previously the only municipality with a multiple-vote race at both levels; it is now
  in-ward only, `max_votes_max` 2 rather than 6. Its registered-candidate list for 2026
  shows only Mayor, City Councillor by ward, and school board trustees.
- **Niagara Falls** — its 3 at-large Regional Councillors are gone. Its 8 at-large *city*
  councillors are unaffected, so nothing changes in this data.

Because these seats never counted toward city `council_size`, the seat-count check cannot
detect their presence or absence — St. Catharines reconciled either way. They have to be
confirmed from election material, not arithmetic.

### Two things worth knowing about this list

**Three municipalities coded `SMD` have a block-vote race.** Kitchener (4), Cambridge (2)
and Waterloo (2) each elect their Region of Waterloo councillors at-large on the municipal
ballot. The `ward_type` code describes only the city-council wards and misses these
entirely. No other region in the file works this way — Durham, Halton, Peel and York elect
their regional councillors by ward or ward-pair, except Markham, Vaughan, Richmond Hill and
Georgina, which are already flagged. Aurora has no separate regional seat at all; its mayor
holds the York Region seat.

**Eight municipalities coded `MMD`/`Mixed` have no multiple-vote race.** Ajax, Brampton,
Clarington, Georgina, Milton, Oakville, Oshawa and Pickering are all double-direct or
paired-ward. These are the rows most likely to be misread as block vote. (Whitby was a
ninth until its 2026 change; it is now `SMD`. Ajax joined the list when `cmb_muns.csv`
was corrected to `MMD`.)

## Corrections

Both upstream sources are maintained by us: the Google Sheet that selects municipalities,
and `cmb_muns.csv` (its own git repo under `CMB Data/auxiliary-data/Master Municipality
List/`). So a correction has two possible homes, and the rule is:

- **An error in the data goes upstream to `cmb_muns.csv`**, where every consumer gets it,
  with the reasoning in the commit message.
- **Only a fact specific to the 2026 cycle stays in `classification-overrides.csv`**, since
  the master list carries no vintage column and describes the municipality as it currently
  stands.

`old_value` in the overrides file is a **precondition, not a comment**:
`get-municipal-data.R` compares it against `cmb_muns.csv` and aborts if they disagree. That
is what stops an override rotting into a no-op that still stamps `revised = TRUE` after the
fix lands upstream.

### Resolved upstream: the Hamilton row was the wrong municipality

Kept for the record — **no override remains for this**; it was fixed at source.

`census_id 3514019` is **Hamilton, Township (TP)** — a ~11,000-person township in
Northumberland County, council size 5, genuinely At-Large. The City of Hamilton is
**`3525005`**, in `cmb_muns.csv` as Ward / SMD with 15 wards. Both have
`csdname = "Hamilton"`, which is how it went unnoticed.

```
3514019 | Hamilton, Township (TP) | council_size 5  | At-Large | N/A
3525005 | Hamilton, City (C)      | council_size 16 | Ward     | SMD
```

The bad ID was in the Google Sheet that supplies `muns$census_id`
(`docs.google.com/spreadsheets/d/1QuW7-3GA6_Gbrohr-mUZUH7rhAjUkNs3i6u8rFxda4Y`). The Sheet
now carries `3525005`, so the temporary `census_id` remap has been removed from
`classification-overrides.csv` and Hamilton is no longer flagged `revised`.

If the Sheet ever regresses, this fails loudly rather than silently: `council-races.csv`
keys Hamilton on `3525005`, so a returning `3514019` trips the id-set check in
`get-municipal-data.R` ("Missing: 3514019. Unexpected: 3525005."). The remap *mechanism*
is still supported by the overrides format — a row with `column == "census_id"` is applied
before the master list is filtered — there just aren't any such rows now.

### Resolved upstream: Ajax was coded SMD but is structurally identical to Pickering

Ajax Town Council is "a mayor, three regional councillors and three ward councillors" over
three wards — six councillors from three districts, so magnitude 2. Pickering, Oshawa,
Milton, Oakville and Brampton all have this structure and are coded `MMD`; Ajax alone was
`SMD` with master `magnitude` 1. `SMD` → `MMD`. `block_vote` stays `FALSE` — both offices
are vote-for-one.

Fixed in `cmb_muns.csv` (commit `1b8c16f`, "Correct Ajax's election type"), so **no
override remains for this either**. Note `magnitude` is still `1` upstream while
`ward_type` is now `MMD` — those two disagree and `magnitude` should be `2`.

The regional councillors **are** members of Ajax Town Council, not regional-only delegates.
Three independent confirmations, since this is the row most easily misread:

1. The Town's Meet Your Mayor & Council roster lists all seven — Mayor Shaun Collier;
   Local Councillors Rob Tyler-Morin (W1), Nancy Henry (W2), Lisa Bower (W3); Regional
   Councillors Marilyn Crawford (W1), Sterling Lee (W2), Joanne Dies (W3).
2. Master `council_size` is 7. Were the regional councillors excluded, town council would
   be the mayor plus three locals — 4.
3. The 2016 Council Composition and Ward Boundary Review kept council "at seven members,
   with three wards in Ajax, each with one Local and one Regional Councillor". Ajax cut
   from four wards to three for 2018 specifically to gain a Durham Regional Council seat,
   which only works under double-direct.

Contrast Cambridge, Kitchener and Waterloo, whose regional councillors sit on regional
council *only* and are therefore excluded from the seat-count check above.

Burlington is *not* the same case and stays `SMD`: its six wards each elect a single "City
and Regional Councillor", one person holding both roles, so magnitude really is 1.

### Resolved upstream: Sarnia's blank `ward_type`

The master list had an empty `ward_type` cell for Sarnia, which `readr` wrote out as a bare
`NA` instead of the `N/A` literal every other at-large row uses. An omission rather than a
cycle-specific fact, so it belonged upstream — fixed in `cmb_muns.csv` (commit `86ec3c6`,
"Correct Sarnia ward_type"), and **no override remains for this**.

The staleness guard is what caught it: the override's blank `old_value` no longer matched
the upstream `N/A`, so the next run aborted rather than silently continuing to overwrite.

### The one active override: Whitby is no longer MMD as of 2026

Whitby's four Regional Councillors were elected at-large through 2022 — a genuine vote-for-4
block race. Council voted to elect them by ward starting with the October 2026 election, so
an elector now casts one vote each for mayor, local ward councillor, and regional ward
councillor. `Hybrid`/`MMD` → `Ward`/`SMD`.

**This is the one genuinely cycle-specific row, and the reason the override layer exists.**
It is not an error: `Hybrid`/`MMD` correctly describes the council sitting today, elected in
2022 under the at-large structure. `Ward`/`SMD` describes the term beginning November 2026.
`cmb_muns.csv` has no vintage column, so it cannot hold both — push this upstream and the
master describes the upcoming term while misdescribing the sitting council; leave it here
and the master stays true to today. It is parked here on the second reading. Revisit after
the October 2026 election, when the new structure simply becomes the current one and the
override should move upstream.

### When this file empties

Whitby is the last row. Once it is folded upstream after the October 2026 election, delete
`classification-overrides.csv` outright, along with the `revised` and `revision_source`
columns it feeds and the override block in `get-municipal-data.R`. Provenance is better
served by the master repo's git history than by a `reason` column; commits `1b8c16f` and
`86ec3c6` on `cmb_muns.csv` are the model. `council-races.csv` is unaffected and stays
hand-maintained either way.

## Known staleness in the upstream master list

Still outstanding. None affects `election_type` / `ward_type`, so none is overridden here —
noted so they are not rediscovered later. (Ajax `magnitude` was on this list and has since
been corrected to `2`.)

- **`cmb_muns.csv` `council_size` for Chatham-Kent is 18**, reflecting the pre-2026 six-ward
  structure. The 2026 structure is 8 wards and 14 councillors plus the mayor.
- **`cmb_muns.csv` has a `magnitude` column** that is close to `seats_per_district`, but it
  reads `Mixed` for exactly the municipalities that matter (Chatham-Kent, Timmins, Markham,
  Vaughan, Richmond Hill, Thunder Bay) and never distinguishes seats from votes.
  `council-races.csv` resolves those cases rather than duplicating the column.
- **Aurora and Haldimand County both changed structure for 2026** — Aurora to a six-ward
  system, Haldimand from six wards to seven. Both remain one councillor per ward, so
  `ward_type` stays correct either way, but Haldimand's `council_size` of 7 still reflects
  six wards; for 2026 it is 8 (mayor plus seven).

## Upper-tier coverage: verified complete

Regional/county seats are easy to miss because they do not count toward city `council_size`,
so the seat check is blind to them. Every two-tier municipality in the file was checked
explicitly for a separately elected upper-tier race:

- **Has one, and its holders also sit on local council** (14): Ajax, Brampton, Burlington,
  Clarington, Georgina, Markham, Milton, Oakville, Oshawa, Pickering, Richmond Hill,
  Sarnia, Vaughan, Whitby. Seats reconcile exactly to `council_size - 1`.
- **Has one, holders sit on the upper tier only** (3): Cambridge, Kitchener, Waterloo.
  These are the seat-count exceptions.
- **Has none** — confirmed, not assumed:
  - *Mississauga* — every member of city council is simultaneously a Peel regional
    councillor; same people, one race, no separate ballot line.
  - *Aurora* — no separate seat; the mayor holds Aurora's York Region seat.
  - *Niagara Falls, St. Catharines* — abolished for 2026, see above.
  - *Bradford West Gwillimbury, Innisfil* — Simcoe County council is the mayors and deputy
    mayors of its 16 member municipalities, ex officio. The deputy mayor is elected
    at-large as a single seat, which is out of scope and would not change `block_vote`.
- **Single-tier, no upper tier at all**: Barrie, Brantford, Chatham-Kent, Greater Sudbury,
  Guelph, Haldimand County, Hamilton, Kingston, London, Ottawa, Peterborough, Thunder Bay,
  Timmins, Toronto, Windsor.

## Confidence notes

Two rows rest on 2022 sources because no 2026 equivalent is published yet:

- **Timmins Ward 5** — the 2022 results table states "4 to be elected" under plurality block
  voting. A referendum on changing the ward system is on the 2026 ballot, but it could not
  take effect before 2030.
- **Sarnia** — the two four-seat at-large contests are documented for 2022; the City's 2026
  page lists both offices but not the seat counts.

Everything else is from a 2026-cycle municipal or regional page.

## Sources

### Multi-member wards
- Brantford — [Brantford City Council (Wikipedia)](https://en.wikipedia.org/wiki/Brantford_City_Council) · [Election FAQ](https://www.brantford.ca/your-government/municipal-election/frequently-asked-questions/)
- Guelph — [Council composition](https://guelph.ca/city-government/mayor-and-council/council-composition-and-ward-boundary-review/city-council-composition/) · [2022 Guelph municipal election (Wikipedia)](https://en.wikipedia.org/wiki/2022_Guelph_municipal_election)
- Peterborough — [Nominations open May 1](https://www.peterborough.ca/news/posts/municipal-election-nominations-open-may-1/)
- St. Catharines — [Ward Councillors](https://www.stcatharines.ca/council-and-administration/mayor-and-council/ward-councillors/) · [St. Catharines City Council (Wikipedia)](https://en.wikipedia.org/wiki/St._Catharines_City_Council)
- Chatham-Kent — [2026 Municipal Election](https://www.chatham-kent.ca/localgovernment/elections/Pages/2026-Municipal-Election.aspx) (per-ward counts quoted directly) · [Ward boundary review](https://www.letstalkchatham-kent.ca/council-composition-and-ward-boundary-review) (8 wards, 14 councillors) · [Chatham Voice](https://chathamvoice.com/2025/02/11/c-k-council-votes-to-shrink/)
- Timmins — [City Council](https://www.timmins.ca/our_services/city_hall/mayor_and_council/city_council) · [2022 Cochrane District elections (Wikipedia)](https://en.wikipedia.org/wiki/2022_Cochrane_District_municipal_elections) · [Timmins City Council (Wikipedia)](https://en.wikipedia.org/wiki/Timmins_City_Council)

### At-large block vote
- Niagara Falls — [2026 Municipal Election](https://niagarafalls.ca/city-government/elections/2026-municipal-election/) · [Niagara Falls City Council (Wikipedia)](https://en.wikipedia.org/wiki/Niagara_Falls_City_Council)
- Niagara regional councillors abolished for 2026 — [Niagara Region, Governance Changes](https://www.niagararegion.ca/government/council/governance-changes.aspx) ("Starting with the October 2026 election, the independently elected Regional Councillors will be eliminated") · [2026 Niagara Region municipal elections (Wikipedia)](https://en.wikipedia.org/wiki/2026_Niagara_Region_municipal_elections) · [St. Catharines Registered Candidates](https://www.stcatharines.ca/council-and-administration/elections/registered-candidates/) (no Regional Councillor office)
- Mississauga upper-tier — [Peel Regional Council (Wikipedia)](https://en.wikipedia.org/wiki/Peel_Regional_Council) · [Guide to Peel Region Council](https://peelregion.ca/sites/default/files/2026-04/guide-to-peel-regional-council.pdf) (all Mississauga councillors are also regional councillors)
- Simcoe County upper-tier — [2022 Simcoe County municipal elections (Wikipedia)](https://en.wikipedia.org/wiki/2022_Simcoe_County_municipal_elections) (county council is the mayors and deputy mayors, ex officio)
- Sarnia — [2026 Election](https://www.sarnia.ca/city-government/elections/2026-election/) · [2022 Lambton County elections (Wikipedia)](https://en.wikipedia.org/wiki/2022_Lambton_County_municipal_elections) (two separate "Four to be elected" races) · [Sarnia City Council (Wikipedia)](https://en.wikipedia.org/wiki/Sarnia_City_Council)
- Thunder Bay — [CBC election day guide](https://www.cbc.ca/news/canada/thunder-bay/election-day-guide-1.6625475) · [Thunder Bay City Council (Wikipedia)](https://en.wikipedia.org/wiki/Thunder_Bay_City_Council)
- Kitchener / Cambridge / Waterloo regional councillors — [2026 Waterloo Region municipal elections (Wikipedia)](https://en.wikipedia.org/wiki/2026_Waterloo_Region_municipal_elections) (Kitchener 4, Cambridge 2, Waterloo 2) · [Global News, voting in the Kitchener municipal election](https://globalnews.ca/news/9217224/kitchener-municipal-election-everything-need-to-know/) ("you can vote for four regional councillor candidates") · [Region of Waterloo 2026 election](https://www.regionofwaterloo.ca/government-and-council/elections/2026-municipal-election/)
- Markham — [About Local Government](https://www.electionsmarkham.ca/en/about-us/about-local-government/) · [Markham City Council (Wikipedia)](https://en.wikipedia.org/wiki/Markham_City_Council)
- Vaughan — [Vaughan City Council (Wikipedia)](https://en.wikipedia.org/wiki/Vaughan_City_Council) · [NewmarketToday, York Region winners](https://www.newmarkettoday.ca/2022-municipal-election-news/heres-a-look-at-municipal-election-winners-around-york-region-6004844)
- Richmond Hill — [Voter Information](https://www.richmondhill.ca/en/living-here/voter-information.aspx) ("up to two" Regional Councillors) · [Richmond Hill City Council (Wikipedia)](https://en.wikipedia.org/wiki/Richmond_Hill_City_Council)

### Vote-for-one despite MMD / Mixed coding
- Ajax — [Ajax Elections, Voters](https://elections.ajax.ca/voters) (3 wards) · [Meet Your Mayor & Council](https://ajax.ca/town-hall/leadership-council/mayor-council/meet-your-mayor-council) (7 members; regional councillors sit on Town Council) · [2016 Council Composition and Ward Boundary Review](https://www.ajax.ca/en/inside-townhall/resources/Documents/GGC-Jun-13-2016-Report---Ajax-Council-Composition-and-Ward-Boundary-Review.pdf)
- Brampton — [2022 Official Results](https://www.brampton.ca/EN/City-Hall/election/Documents/2022%20Brampton%20Municipal%20Election%20-%20Official%20Results.pdf) ("Vote For 1") · [Brampton City Council (Wikipedia)](https://en.wikipedia.org/wiki/Brampton_City_Council)
- Milton — [Nominations open May 1](https://www.milton.ca/en/news/nominations-for-the-2026-municipal-election-open-may-1.aspx)
- Oakville — [Offices to be Elected](https://www.oakville.ca/town-hall/elections/voters/offices-to-be-elected/) ("Seven to be elected, one in each ward" for both councillor offices)
- Oshawa — [Voters](https://www.oshawa.ca/en/city-hall/voters.aspx)
- Pickering — [Offices to be Elected](https://www.pickering.ca/council-city-administration/elections/offices-to-be-elected/)
- Clarington — [2026 Durham Region municipal elections (Wikipedia)](https://en.wikipedia.org/wiki/2026_Durham_Region_municipal_elections)
- Georgina — [2026 Election](https://www.georgina.ca/municipal-government/2026-election) ("one vote for each office")
- Whitby — [Council votes to elect Regional Councillors by ward](https://www.whitby.ca/news/posts/whitby-council-votes-to-elect-regional-councillors-by-ward/)

### Single-member ward counts
(Ajax is listed above — it is MMD, not SMD.)
- Aurora — [Aurora's Ward System](https://www.aurora.ca/your-government/elections-2026/auroras-ward-system/) (6 wards) · [York Regional Council (Wikipedia)](https://en.wikipedia.org/wiki/York_Regional_Council) (no separate regional seat)
- Barrie — [City Council](https://www.barrie.ca/government-news/mayor-council-committees/city-council) (10)
- Bradford West Gwillimbury — [Council Members](https://www.townofbwg.com/town-hall/council/council-members/) (7)
- Burlington — [Council Members and Wards](https://www.burlington.ca/en/council-and-city-administration/council-members-and-wards.aspx) (6)
- Cambridge — [Cambridge City Council (Wikipedia)](https://en.wikipedia.org/wiki/Cambridge_City_Council_(Ontario)) (8)
- Greater Sudbury — [City Council](https://www.greatersudbury.ca/city-hall/mayor-and-council/city-council/) (12)
- Haldimand County — [Seven ward model for 2026](https://www.haldimandcounty.ca/news/posts/haldimand-county-adopting-seven-ward-model-for-2026-municipal-election/) (7, up from 6)
- Hamilton — [City Council Members](https://www.hamilton.ca/city-council/council-committee/city-council-members) (15)
- Innisfil — [Council Members and Wards](https://innisfil.ca/en/my-government/council-members-and-wards.aspx) (7)
- Kingston — [2026 Ontario municipal elections, Southern Ontario (Wikipedia)](https://en.wikipedia.org/wiki/2026_Ontario_municipal_elections_in_Southern_Ontario) (12 districts)
- Kitchener — [Kitchener City Council (Wikipedia)](https://en.wikipedia.org/wiki/Kitchener_City_Council) (10)
- London — [2026 London municipal election (Wikipedia)](https://en.wikipedia.org/wiki/2026_London,_Ontario,_municipal_election) (14)
- Mississauga — [Mississauga City Council (Wikipedia)](https://en.wikipedia.org/wiki/Mississauga_City_Council) (11)
- Ottawa — [Voting for Mayor and City Councillor](https://ottawa.ca/en/city-hall/elections/voters/voting-mayor-and-city-councillor) (24)
- Toronto — [2026 Toronto municipal election (Wikipedia)](https://en.wikipedia.org/wiki/2026_Toronto_municipal_election) (25)
- Waterloo — [Find your councillor and ward](https://www.waterloo.ca/council-and-committees/mayor-and-city-council/find-your-councillor-and-ward/) (7)
- Windsor — [Ward 2, Windsor (Wikipedia)](https://en.wikipedia.org/wiki/Ward_2_(Windsor,_Ontario)) (10, since 2010)
