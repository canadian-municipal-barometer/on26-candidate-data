#!/usr/bin/env python3
"""Harvest trustee candidates from a candidate list built as labelled headings + tables.

Usage: python3 scripts/harvest-accordion.py --page FILE --census-id ID --csdname NAME
                                            [--out FILE]
       python3 scripts/harvest-accordion.py --batch DIR [--out FILE]

Resolves the repo root from its own path. No dependencies.

WHY THIS SHAPE GETS ITS OWN SCRIPT. The commonest municipal candidate-list layout is a
label followed by a table of candidates - as an accordion button (Hamilton: 38 tables over
11 English public and 9 English Catholic zones) or as a plain heading. The general crawler
cannot read either, because the label is the only place the contest is named and the table
carries no id or caption of its own. It is worth a script rather than a by-hand read
because the tables themselves are clean, usually Name / Address / Phone / Email - which is
also where most of the contact information in this dataset lives.

LABELS COME FROM THREE PLACES, tried in order: the table's OWN <caption>, an accordion
toggle button, and any heading element (h1-h6, summary, th spanning the table, or a bolded
paragraph) that precedes a table. Whichever is found, it is combined with the nearest
preceding section heading that mentions a trustee - see BOARD RESOLUTION.

A THIRD PLACE THE LABEL HIDES is the table's own header row. Terrace Bay, Manitouwadge and
Marathon share a regional template whose first row reads

    | Superior North Catholic District School Board (English Separate) | Date Filed | Time | Contact Info. |

- the contest in the first cell and the column headers beside it. Dryden writes the same
idea with one cell and no columns at all:

    | English Separate School Board Trustee - Two (2) to be elected Northwest Catholic District School Board |
    | Bryck , Kathy |

There is no caption, no button and no heading on either, so a reader that only looks above
the table finds the page's last unrelated heading and classifies the contest as whatever
that said. A first cell that classifies to a board or a system is therefore taken as the
label, and that row is then not read as a candidate. Like the caption this is a label the
table carries itself, so it beats anything found by position; unlike the caption it is only
accepted when it NAMES something, because an ordinary header row's first cell is "Name" and
must go on meaning nothing. That test is also what makes the row count irrelevant - a lone
spanning cell is as good a label as a first-of-four, and a candidate's name classifies to
nothing either way.

THE CAPTION HAS TO BE READ FIRST, and reading it as just another preceding element was a
bug that cost six municipalities their whole list. A <caption> is a CHILD of the table it
labels, so it opens AFTER the table does - and the scan below pairs a table with the
nearest label that ENDS BEFORE the table starts. A caption therefore never labelled its own
table; it labelled the NEXT one, shifting every label on the page by one. On Haldimand
County's page that put "Grand Erie Public School Board candidates" on the table after the
Grand Erie one and left the real trustee tables labelled "Ward 7 candidates", so the whole
page classified as council and yielded nothing. Central Elgin, Bayham, Clearview, North
Dumfries and Arnprior are the same shape. Captions are correct, ordinary HTML; the reader
was wrong.

The page is read from a LOCAL FILE rather than fetched, so the harvest is reproducible and
the fetch stays a separate, visible step. --batch reads a whole directory of pages named
<census_id>.html, which is what scripts/crawl-municipal-elections.py writes.

CONTACT IS READ TWICE, because these pages disagree about where it goes. First by column,
matched on header text rather than position - anything containing "mail" is the email
column, "phone"/"tel" the phone, "web"/"site" the website. Then, for whatever is still
blank, by scanning the whole row: many clerks put "Email: someone@example.com" inline in
the name cell instead of giving it a column, and a column-only read finds nothing on those
pages even though every candidate has an address on them. The row scan is the fallback, not
the primary, so a proper column always wins.

WITHDRAWN NOMINATIONS. These pages mark them inline on the name - "Noble, Jonathan
(WITHDRAWN)" and "McMullin, Shawn - WITHDRAWN" both occur on Hamilton's page, in different
shapes. They are dropped and counted, per this repo's rule that a withdrawn nomination is
not part of the dataset. The marker is stripped from the name before the drop is decided,
so a candidate is never kept with "- WITHDRAWN" embedded in their name.

A clerk can also say it ONCE, in the heading over a whole table - Haldimand County gives
withdrawn candidates their own accordion next to the live one, with the names inside
written perfectly normally. A per-name rule reads every one of them as a candidate, and
one did reach the frame that way (Toni Poirier, Grand Erie, in the 2026-08-27 build). The
heading is therefore checked before any row is read.

A TABLE CAN ALSO CARRY THE CONTEST IN A COLUMN, one row per candidate and the office
beside the name rather than above the table:

    | Office                                                    | Name of Candidate | Qualifying Address |
    | Mayor                                                     | LAFERRIERE, Jeff  | 335 Browning St... |
    | School Board Trustee - English Separate Northeastern C... | DRAINVILLE, Martin| 94 Cross Lake Rd...|

Nothing labels this table, and the label reader above cannot help: there is no single
contest to label it with, because the council and trustee races share one table. So a
second pass reads any table whose header row names BOTH an office-ish column and a name
column, classifies each ROW on its own office cell, and keeps the rows that classify to a
board. Six of the crawled pages are this shape - Emo, Temiskaming Shores, Central Elgin,
Tay Valley, Whitestone and Killarney - and none of them yielded anything before.

The name column is found by its header rather than assumed to be first, which is the whole
point: `cells[0]` here is the office, and reading it as a name is why these pages produced
nothing rather than producing rubbish.

Two candidates can also share one cell. Temiskaming Shores puts both of its English public
trustees in a single row as "WILKINSON, Brigid WIWCHAR, Larry", so a cell is split wherever
an ALL-CAPS word followed by a comma starts a new name. That is a narrow rule on purpose:
it needs the surname-comma shape these sources use, so "Van Milligen, Matthew" and
"MEED WARD, Marianne" stay whole.

A TABLE CAN CHANGE CONTEST HALFWAY DOWN, and reading its label as binding for every row
files candidates under the wrong board. Stone Mills publishes all four of its trustee
contests in ONE table, each introduced by a row holding a single spanning cell:

    | English Public Trustee (Limestone District School Board) ... |   <- the table's label
    | Isabella Harpell        | Phone: ... | August 21, 2026 |
    | Robin Hutcheon          | Phone: ... | August 20, 2026 |
    | English Separate Trustee (Algonquin & Lakeshore ...)         |   <- a NEW contest
    | Jacqueline Fernandes (ACCLAIMED) | Phone: ... | August 18, 2026 |
    | French Public Trustee (Conseil des ecoles publiques ...)     |   <- and another

Taking the first row as the whole table's label put all six names under Limestone - a
Catholic candidate under a public board, and two French-board candidates in a frame that
excludes French boards entirely. So a row whose only non-empty cell classifies to a
contest is read as a sub-heading: it switches the contest for the rows below it, and a
sub-heading that classifies to nothing (French, or not a trustee race) switches the table
OFF until the next one that does. One table can therefore yield several contests, or none.

A single cell is only read as a sub-heading if it LOOKS like one - see is_heading_cell().
Thunder Bay alternates a name row with a details row, and Ryan Sitch's details row is
"807-252-5485 trustee@rsitch.net": it contains the word trustee, so a bare keyword test
read it as a heading and switched the table off one row before the last candidate on the
page. An address, a phone number or a paragraph of biography is not a heading.

WHAT IS REJECTED AS NOT-A-NAME. A table cell is not always a candidate. Three things get
past a naive read and each costs a wasted or wrong survey invitation, so each is rejected:

  a header row that the header detector missed ("Candidate Name", "Trustee Candidate
    Name", "Date");
  a whole record crammed into the name cell - the District School Board of Niagara's page
    renders "Mark Bagu Nomination Filed: May 29, 2026 Qualifying Address..." as one cell,
    so the name is cut at the first record keyword and kept only if what remains looks
    like a name;
  boilerplate sentences that happen to sit in a table row ("Mayor and, by virtue of
    office, Regional Councillor").

A NAME MUST HAVE TWO WORDS to survive this, which is a deliberate trade. It costs the rare
candidate a source published under a single name - the council data has one such case,
Toronto's "Nisha Kumari," - and in exchange it removes every one-word menu label in one
rule. Any such candidate has to be added by hand; that is the right way round for a frame
whose errors are invitations sent to nobody.

OBFUSCATED EMAILS. Pages behind Cloudflare's email protection render the literal string
"[email protected]" in place of the address. It is not an address, and storing it would
put an undeliverable value in a frame whose whole purpose is contact - so it is discarded
and the candidate is recorded as having no email.

BOARD RESOLUTION happens in two steps, because a button alone does not say enough.

  A button often reads just "Ward 3 - English Public" - no word "trustee" anywhere - while
  the heading above the whole accordion reads "School Board Trustee - English Public". Read
  on its own the button is indistinguishable from the council's "Ward 3", so each button is
  classified together with the nearest preceding section heading that mentions a trustee.
  Without this the run finds nothing at all, which is exactly what it did first time.

  That combined label still names a SYSTEM and not a board. classify() returns
  UNRESOLVED-public, and notes/board-jurisdictions.csv turns that into a board using the
  municipality. The lookup happens here when the crosswalk knows the municipality, and is
  left unresolved when it does not.

  THE SECTION HEADING IS A FALLBACK, NOT AN OVERRIDE, which is the second thing that had to
  be fixed. It is the nearest preceding trustee heading and it is sticky: it applies to
  every table below it until another one replaces it. On a page that lists the French
  boards above the English ones - Cambridge, Hanover and Haldimand all do - that heading is
  a French one, and prefixing it to an English table's label made classify() return
  french-language-board and drop a contest that was never French. So the label is now
  classified on its own FIRST and the heading consulted only if that says nothing; and
  where the heading is French while the table's label is not, the label is retried with a
  neutral "School Board Trustee" in place of it. That supplies the one word the label is
  missing without importing a language it never claimed. A label naming neither a board nor
  a system still classifies to nothing, so this cannot promote a council table.
"""
import argparse
import csv
import html
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trustee_boards import classify  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JURIS = os.path.join(REPO, "notes", "board-jurisdictions.csv")

# Both shapes seen in the wild, on one page.
WITHDRAWN = re.compile(r"\s*[-(]\s*WITHDRAWN\s*\)?\s*$", re.I)
# A whole table of them, said in the heading instead of on each name: Haldimand County
# publishes "Grand Erie Public School Board withdrawn candidates" as its own accordion
# beside the live one. Every name under such a heading is a withdrawal, however tidily it
# is written.
WITHDRAWN_SECTION = re.compile(r"withdraw", re.I)
# The other status marker these pages put on the name itself, in as many shapes as they put
# WITHDRAWN in: "Danaher, John - ACCLAIMED", "Gardhouse, Guy (Acclaimed)", "DiMenna, Mary
# ( Acclaimed )*", "Dametto-Giovannozzi, Paula - Acclaimed Acclamation Form" (the tail is a
# link to the form). Unlike a withdrawal it does not disqualify the record - it IS the
# acclamation flag - so it is moved off the name into `acclaimed` rather than dropped.
# Leaving it on the name puts "- ACCLAIMED" in the salutation of a survey invitation and
# reads the flag as 0 for someone who was acclaimed; 21 rows of the 2026-08-27 frame had
# both faults.
ACCLAIMED = re.compile(r"\s*[-\u2013\u2014]?\s*\(?\s*acclaimed\s*\)?\s*\*?"
                       r"\s*(?:acclamation\s+form\s*)?$", re.I)
CELL_EMPTY = re.compile(r"^-?$")


def txt(s):
    s = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
    # Sources that wrap each name part in its own element leave a space before the comma
    # once the tags are stripped - Dryden yields "Gauthier , Barbara". The comma is the
    # separator this repo's names are built on and the string reaches a survey salutation
    # verbatim, so close it up here rather than in every reader downstream.
    return re.sub(r"\s+([,;])", r"\1", s)


# A heading that introduces a run of trustee accordions. Kept broad - the point is only to
# supply the words the button omits.
SECTION_HEAD = re.compile(
    r"(?is)<(?:p|h[1-6]|strong|legend)[^>]*>((?:(?!</?(?:p|h[1-6]|strong|legend)).){0,200}?"
    r"(?:trustee|school board)(?:(?!</?(?:p|h[1-6]|strong|legend)).){0,200}?)</(?:p|h[1-6]|strong|legend)>")


# Anything that can carry a contest label immediately above its table. `caption` is NOT
# here: a caption belongs to the table it sits inside and is read by CAPTION below, not by
# position. See THE CAPTION HAS TO BE READ FIRST.
LABEL_EL = re.compile(
    r'(?is)<button[^>]*accordion[^>]*>(.*?)</button>'
    r'|<(?:h[1-6]|summary|legend)[^>]*>(.*?)</(?:h[1-6]|summary|legend)>'
    r'|<p[^>]*>\s*<strong[^>]*>(.*?)</strong>\s*</p>')

# A table's own label, which beats anything found by position.
CAPTION = re.compile(r"(?is)<caption[^>]*>(.*?)</caption>")
FIRST_ROW = re.compile(r"(?is)<tr[^>]*>(.*?)</tr>")
CELLS = re.compile(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>")


def header_label(table_html):
    """Return (label, is_french) for the contest named in a table's first cell.

    Only a cell that classify() recognises becomes a label - see A THIRD PLACE THE LABEL
    HIDES. A cell naming a FRENCH board is reported separately rather than ignored: the
    table belongs to a board this dataset excludes, and saying nothing lets the label fall
    back to whatever sits above the table. Ingersoll is the case - its "Conseil Scolaire
    Catholique Providence" table took the London District Catholic heading from further up
    the page, and a French separate trustee reached the frame as an English Catholic one.
    """
    m = FIRST_ROW.search(table_html)
    if not m:
        return "", False
    cells = CELLS.findall(m.group(1))
    if not cells:
        return "", False
    first = txt(cells[0])
    if not first:
        return "", False
    board, _system, reason = classify(first)
    # The length cap is about not mistaking a paragraph for a label. It has no bearing on
    # whether the table is French: Ingersoll spells the contest out in 160 characters -
    # "Conseil Scolaire Catholique Providence (One to be elected by French language separate
    # school electors to represent the Counties of Oxford, Elgin, and Middlesex)" - and
    # capping first meant the table was read after all, under the heading above it.
    if reason == "french-language-board":
        return "", True
    if len(first) > 140:
        return "", False
    return (first, False) if board is not None else ("", False)


def sections(doc):
    """Yield (label with context, bare label, table html, skip_header) for each labelled table.

    skip_header says the first row supplied the label and is not a candidate row.
    The section heading matters as much as the label: see BOARD RESOLUTION.
    """
    heads = [(m.start(), txt(m.group(1))) for m in SECTION_HEAD.finditer(doc)]
    labels = [(m.start(), m.end(), txt(next(g for g in m.groups() if g is not None)))
              for m in LABEL_EL.finditer(doc)
              if any(g is not None for g in m.groups())]
    tables = list(re.finditer(r"(?is)<table.*?</table>", doc))

    for t in tables:
        own = CAPTION.search(t.group(0))
        head_label, head_french = header_label(t.group(0))
        if head_french:
            continue                  # a French board's own table; see header_label()
        skip_header = False
        if own:
            label = txt(own.group(1))
        elif head_label:
            label, skip_header = head_label, True
        else:
            # nearest label that ends before this table starts
            cand = [l for l in labels if l[1] <= t.start()]
            if not cand:
                continue
            pos, end, label = cand[-1]
            # a label separated from its table by another table is not its label
            if any(x.start() > end and x.end() < t.start() for x in tables):
                continue
        if not label or len(label) > 120:
            continue
        head = ""
        for hpos, htext in heads:
            if hpos < t.start():
                head = htext
            else:
                break
        yield (f"{head} - {label}" if head else label), label, t.group(0), skip_header


EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Cloudflare's placeholder, and anything else that is a label rather than an address.
BAD_EMAIL = re.compile(r"email\s*protected|^\s*$", re.I)
# Where a page crams the whole record into the name cell, the name ends here.
RECORD_NOISE = re.compile(
    r"\s*(nomination\s+filed|qualifying\s+address|date\s+filed|e-?mail|telephone|phone|"
    r"website|please\s+note|the\s+above\s+candidate)\b.*$"
    # A footnote on the name saying which clerk certified a trustee whose zone crosses the
    # municipal boundary: Bluewater prints "Marnie Van Esbroeck *Certified by South Huron
    # Clerk". It is about the nomination, not part of the name, and the same person appears
    # unannotated elsewhere on the page - so left in it becomes a second candidate.
    r"|\s*\*?\s*certified\s+by\b.*$", re.I)
# A header row the header detector did not catch, or boilerplate.
NOT_A_CANDIDATE = re.compile(
    r"^(trustee\s+)?(candidate\s*name|name|date|office|ward|position|contact|information|"
    r"school\s+board.*|the\s+.*)$"
    # A header row that says more than the bare word. Middlesex Centre heads both its
    # trustee tables "Name of Candidate (in alphabetical order)", which the anchored
    # alternatives above cannot reach because of the trailing parenthesis.
    r"|^(name\s+of\s+candidates?|candidates?\s+names?)\b.*"
    # ...and the same thing said the other way round. Port Colborne labels each table with
    # the candidate's name and puts the board in the first row, so "English Language Public
    # District School Board" arrives where a person should be. No one is named for a board.
    r"|.*\bschool\s?board\s*$"
    # NOT_A_CANDIDATE is used with .match(), so an alternative meant to fire anywhere in the
    # cell needs its own leading .* - as this one and the next both do.
    r"|.*by\s+virtue\s+of\s+office", re.I)
# A plausible person name after trimming: at least two words, not absurdly long.
LOOKS_LIKE_NAME = re.compile(r"^[^\d]{3,60}$")
# A table's own label that is not a contest label at all. The label scan takes the nearest
# heading-shaped element above a table, and on a page that gives its tables no headings
# that is a column header or a status marker - East Garafraxa yields "Date Filed" and
# "(Acclaimed)". Combined with the board heading further up the page it classifies as a
# real contest, which is how eight council candidates reached the trustee frame.
# A bare "Name" is deliberately NOT here: Leeds and the Thousand Islands labels its real
# trustee table with its own column header, under a section heading that names the board,
# and two candidates ride on it.
NOT_A_LABEL = re.compile(r"^\(?\s*(date\s+filed|contact\s+information|acclaimed|"
                         r"nomination\s+filed|qualifying\s+address|e-?mail|phone|"
                         r"telephone|website|address|status)\s*\)?\s*\*?$", re.I)
# A label naming a council seat is a council table however trustee-ish the heading above it
# is - East Garafraxa's "Municipal Council (Certified Candidates)" sits under a Dufferin
# Peel Catholic heading. A label that names a trustee seat as well is left alone, since
# some clerks head one table with both.
COUNCIL_LABEL = re.compile(r"\b(municipal\s+council|mayor|reeve|warden|councillor|"
                           r"council\s+member|member\s+of\s+council)\b", re.I)
TRUSTEE_LABEL = re.compile(r"trustee|school\s?board", re.I)
PHONE_RX = re.compile(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}")
# Header cells that mean "this column holds the contest" and "this column holds the person".
OFFICE_COL = re.compile(r"^(office|position|contest|seat)\b", re.I)
NAME_COL = re.compile(r"^(name|candidate)\b|\bname\b", re.I)
# A source that splits the name across two columns: Brockville heads them LAST NAME and
# FIRST NAME. Read together they give the "Last, First" this repo stores; read as one
# column they give a bare surname, which is how "Lalonde Pankow" lost her given name.
LAST_COL = re.compile(r"^(last|surname|family)\s*name\b|^surname$", re.I)
FIRST_COL = re.compile(r"^(first|given)\s*name\b", re.I)
# A RESULTS table is not a candidate list, and municipalities publish both on one page -
# Brockville, East Garafraxa and Killarney all do. Every name in the 2022 results read as a
# 2026 candidate: Killarney's Alex Cimino and Claire Morrison polled 35 and 68 votes in
# 2022 and arrived in the frame beside its actual 2026 trustees.
#
# The test is the DATA, not the header. A header alone is not enough in either direction:
# East Garafraxa heads the column "Votes" and Killarney "Number of Votes", so no single
# spelling catches both, and a candidate list published before voting day could carry an
# empty vote column that means nothing. So a votes-ish column is located by its header and
# the table is refused only if that column actually holds a count. A candidate list has no
# vote counts in it; a table that does is about an election already held. An `elected`
# column is refused on the header alone - there is no innocent reading of it.
VOTES_COL = re.compile(r"\bvotes?\b|\bvote\s*count\b|\bpoll(ed|s)?\b", re.I)
ELECTED_COL = re.compile(r"\b(elected|winner|result)s?\b", re.I)
VOTE_COUNT = re.compile(r"^\d[\d,\s]*$")
# Acclamation said once for a whole table, in its header: Bluewater heads a column "Name of
# Acclaimed Candidate". Every row under it is an acclamation however the name is written.
ACCLAIMED_HEADER = re.compile(r"acclaim", re.I)
# ...and said in front of the name rather than after it, which the end-anchored ACCLAIMED
# above cannot see: Clearview writes "ACCLAIMED Brandy Rafeek".
ACCLAIMED_PREFIX = re.compile(r"^\s*\(?\s*acclaimed\s*\)?\s*[-\u2013\u2014:]?\s*", re.I)
# Two names in one cell: a new one starts at an ALL-CAPS word followed by a comma.
SPLIT_NAMES = re.compile(r"(?<=[a-z.\)])\s+(?=[A-Z\u00C0-\u00DD][A-Z\u00C0-\u00DD'\u2019.\- ]{1,30},)")
SITE_RX = re.compile(r"https?://[^\s\x22\x27<>]+")


def rows(table_html):
    """Yield (cells, raw row html) so contact can be read by column or by row scan."""
    for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", table_html):
        cells = [txt(c) for c in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", tr)]
        if cells:
            yield cells, tr


def col_index(header):
    """Map contact fields to column positions by what the header says, not where it sits."""
    idx = {}
    for i, h in enumerate(header or []):
        h = (h or "").lower()
        if "mail" in h and "email" not in idx:
            idx["email"] = i
        elif ("phone" in h or "tel" in h) and "phone" not in idx:
            idx["phone"] = i
        elif ("web" in h or "site" in h) and "website" not in idx:
            idx["website"] = i
        elif "address" in h and "address" not in idx:
            idx["address"] = i
    return idx


def classify_label(bare, combined):
    """Classify a table's label, using the section heading only where it has to.

    See THE SECTION HEADING IS A FALLBACK in the module docstring. Returns the first of
    three readings that names a board or a system.
    """
    for candidate, how in ((bare, "label"),
                           (combined, "label+section"),
                           (f"School Board Trustee - {bare}", "label+neutral-trustee")):
        board, system, reason = classify(candidate)
        if board is not None:
            return board, system, f"{reason}({how})"
    return None, None, "unclassified"


def is_heading_cell(text):
    """Could this lone cell be a contest heading, rather than a record or a sentence?

    A heading is short and says nothing else. Contact details disqualify it outright: the
    sources that put a whole record in one cell always include an address, a phone or an
    email, and the word "trustee" inside one of those (trustee@example.com, "I am currently
    a trustee") is not a heading. See A TABLE CAN CHANGE CONTEST HALFWAY DOWN.
    """
    t = (text or "").strip()
    return bool(t) and len(t) <= 140 and not EMAIL_RX.search(t) \
        and not SITE_RX.search(t) and len(re.findall(r"\d", t)) <= 3


def fold_office(label):
    """A contest label reduced to what two readers would agree on."""
    return re.sub(r"[^a-z0-9]+", " ", (label or "").lower()).strip()


def clean_candidate(name, cells, raw_row, idx, acclaimed_table=False):
    """Turn one table row into a candidate record, or None if it is not a person.

    Shared by both readers so the WITHDRAWN / ACCLAIMED / not-a-name rules and the
    two-pass contact read apply identically however the contest was labelled. Returns
    (record, dropped_withdrawn).
    """
    if not name or CELL_EMPTY.match(name):
        return None, 0
    if WITHDRAWN.search(name):
        return None, 1
    acclaimed = bool(ACCLAIMED.search(name)) or bool(ACCLAIMED_PREFIX.match(name))
    if acclaimed:
        name = ACCLAIMED_PREFIX.sub("", ACCLAIMED.sub("", name)).strip()

    def val(k):
        i = idx.get(k)
        if i is None or i >= len(cells):
            return ""
        v = cells[i]
        return "" if CELL_EMPTY.match(v or "") else v

    email, phone, site = val("email"), val("phone"), val("website")
    row_text = txt(raw_row)
    mailtos = re.findall(r"mailto:([^\x22\x27?>]+)", raw_row)
    if not email:
        hit = mailtos or EMAIL_RX.findall(row_text)
        if hit:
            email = hit[0].strip()
    if not phone:
        hit = PHONE_RX.findall(row_text)
        if hit:
            phone = hit[0].strip()
    if not site:
        hit = [u for u in SITE_RX.findall(raw_row) if "mailto" not in u]
        if hit:
            site = hit[0].strip()
    if email and BAD_EMAIL.search(email):
        email = ""
    name = EMAIL_RX.sub("", name)
    name = RECORD_NOISE.sub("", name).strip(" |,-\u2013\u2014")
    if (not name or NOT_A_CANDIDATE.match(name)
            or not LOOKS_LIKE_NAME.match(name)
            or len(name.split()) < 2):
        return None, 0
    return {"name_raw": name, "acclaimed": acclaimed or acclaimed_table,
            "email": email, "phone": phone,
            "address": val("address"), "links": [site] if site else []}, 0


def office_column_tables(doc, census_id, juris):
    """Read tables that name the contest in a column rather than above the table.

    See A TABLE CAN ALSO CARRY THE CONTEST IN A COLUMN. Rows are classified one at a time
    and grouped by the office they name, so a table mixing council and trustee races
    contributes only its trustee rows.
    """
    out, dropped = [], 0
    for t in re.finditer(r"(?is)<table.*?</table>", doc):
        table = t.group(0)
        all_rows = list(rows(table))
        if len(all_rows) < 2:
            continue
        header = [c.lower() for c in all_rows[0][0]]
        if len(header) < 2:
            continue
        if any(ELECTED_COL.search(h) for h in header):
            continue                  # see VOTES_COL: no innocent reading of "elected"
        i_votes = next((i for i, h in enumerate(header) if VOTES_COL.search(h)), None)
        if i_votes is not None and any(
                VOTE_COUNT.match(c[i_votes].strip())
                for c, _r in all_rows[1:] if i_votes < len(c) and c[i_votes].strip()):
            continue                  # the vote column holds counts - a results table
        i_off = next((i for i, h in enumerate(header) if OFFICE_COL.match(h)), None)
        i_last = next((i for i, h in enumerate(header) if LAST_COL.search(h)), None)
        i_first = next((i for i, h in enumerate(header) if FIRST_COL.search(h)), None)
        if i_last is not None and i_first is not None and i_last != i_first:
            i_name = None             # the name is two columns; see LAST_COL
        else:
            i_last = i_first = None
            i_name = next((i for i, h in enumerate(header) if NAME_COL.search(h)), None)
        if i_off is None or (i_name is None and i_last is None) or i_off == i_name:
            continue
        acclaimed_table = any(ACCLAIMED_HEADER.search(h) for h in header)
        idx = col_index(header)
        by_office = {}
        for cells, raw_row in all_rows[1:]:
            need = [i for i in (i_off, i_name, i_last, i_first) if i is not None]
            if max(need) >= len(cells):
                continue
            office = cells[i_off]
            board, system, reason = classify(office)
            if board is None:
                continue
            # Killarney puts the marker on the CONTEST - "SCHOOL BOARD TRUSTEE: English
            # Public - ACCLAIMED" - rather than on the name or in the header.
            office_acclaimed = bool(re.search(r"(?i)\bacclaim", office))
            if str(board).startswith("UNRESOLVED") and system:
                known = juris.get((census_id, system), [])
                if len(known) == 1:
                    board, reason = known[0], "resolved-from-jurisdictions"
            if str(board).startswith(("UNRESOLVED", "AMBIGUOUS")):
                continue
            if i_last is not None:
                last, first = cells[i_last].strip(), cells[i_first].strip()
                pieces = [f"{last}, {first}" if last and first else (last or first)]
            else:
                pieces = SPLIT_NAMES.split(cells[i_name])
            for piece in pieces:
                rec, d = clean_candidate(piece.strip(), cells, raw_row, idx,
                                         acclaimed_table or office_acclaimed)
                dropped += d
                if rec:
                    by_office.setdefault((office, board, system, reason), []).append(rec)
        for (office, board, system, reason), cands in by_office.items():
            out.append({"census_id": census_id, "csdname": "", "county_mun": "",
                        "office": office, "office_context": office,
                        "board_number": board, "system": system,
                        "classify_reason": f"{reason}(office-column)",
                        "empty_notice": False, "candidates": cands})
    return out, dropped


def harvest_page(path, census_id, csdname, juris):
    doc = open(path, encoding="utf-8", errors="replace").read()
    out, dropped = [], 0
    for label, button_label, table, skip_header in sections(doc):
        board, system, reason = classify_label(button_label, label)
        if board is None:
            continue
        if NOT_A_LABEL.match(button_label) or (COUNCIL_LABEL.search(button_label)
                                               and not TRUSTEE_LABEL.search(button_label)):
            continue
        if WITHDRAWN_SECTION.search(button_label) or WITHDRAWN_SECTION.search(label):
            dropped += sum(1 for cells, _ in rows(table)
                           if cells[0] and not CELL_EMPTY.match(cells[0])
                           and not re.match(r"(?i)\s*name", cells[0]))
            continue
        if str(board).startswith("UNRESOLVED") and system:
            known = juris.get((census_id, system), [])
            if len(known) == 1:
                board, reason = known[0], "resolved-from-jurisdictions"

        header, idx = None, {}
        # The contest in force for the rows being read. A sub-heading row replaces it; see
        # A TABLE CAN CHANGE CONTEST HALFWAY DOWN.
        here = (button_label, board, system, reason)
        by_contest = {}
        for n_row, (cells, raw_row) in enumerate(rows(table)):
            if n_row == 0 and skip_header:
                header = [c.lower() for c in cells]
                idx = col_index(header)
                continue
            if header is None and re.match(r"(?i)\s*name", cells[0] or ""):
                header = [c.lower() for c in cells]
                idx = col_index(header)
                continue
            filled = [c for c in cells if c and not CELL_EMPTY.match(c)]
            # A French heading switches the table off however long it runs; see header_label().
            if (len(filled) == 1 and len(filled[0]) <= 400
                    and classify(filled[0])[2] == "french-language-board"):
                here = (filled[0], None, None, "sub-heading-french-board")
                continue
            if len(filled) == 1 and is_heading_cell(filled[0]):
                # Classified ON ITS OWN, never with the section heading prefixed: that
                # context names a board, so every candidate's name would inherit it and
                # read as a sub-heading. Dryden lists one name per single-cell row, and
                # "Northwest Catholic District School Board - Gauthier, Barbara" duly
                # classified as a contest and swallowed the candidate.
                sub_board, sub_system, sub_reason = classify(filled[0])
                if sub_board is not None:
                    if str(sub_board).startswith("UNRESOLVED") and sub_system:
                        known = juris.get((census_id, sub_system), [])
                        if len(known) == 1:
                            sub_board, sub_reason = known[0], "resolved-from-jurisdictions"
                    here = (filled[0], sub_board, sub_system, sub_reason)
                    continue
                if (sub_reason == "french-language-board"
                        or TRUSTEE_LABEL.search(filled[0])
                        or COUNCIL_LABEL.search(filled[0])):
                    # A heading this reader cannot place - a French board, or a council
                    # seat. Everything under it belongs to neither, so stop collecting.
                    here = (filled[0], None, None, "sub-heading-out-of-scope")
                    continue
            if here[1] is None or str(here[1]).startswith(("UNRESOLVED", "AMBIGUOUS")):
                continue
            # Contact is read by column and then by row scan; see CONTACT IS READ TWICE.
            rec, d = clean_candidate(cells[0], cells, raw_row, idx)
            dropped += d
            if rec:
                by_contest.setdefault(here, []).append(rec)

        for (office, bn, system_, reason_), cands in by_contest.items():
            out.append({"census_id": census_id, "csdname": csdname, "county_mun": "",
                        "office": office, "office_context": label,
                        "board_number": bn, "system": system_,
                        "classify_reason": reason_, "empty_notice": False,
                        "candidates": cands})

    # Second pass: tables that name the contest in a column instead of above themselves.
    # Anything already read above is skipped, so a page cannot contribute a contest twice.
    seen = {(c["board_number"], fold_office(c["office"])) for c in out}
    extra, extra_dropped = office_column_tables(doc, census_id, juris)
    for c in extra:
        if (c["board_number"], fold_office(c["office"])) in seen:
            continue
        c["csdname"] = csdname
        out.append(c)
    return out, dropped + extra_dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page")
    ap.add_argument("--census-id")
    ap.add_argument("--csdname")
    ap.add_argument("--batch", help="directory of <census_id>.html pages")
    ap.add_argument("--out")
    a = ap.parse_args()
    if not a.batch and not (a.page and a.census_id and a.csdname):
        ap.error("give --batch DIR, or --page with --census-id and --csdname")

    juris = {}
    if os.path.exists(JURIS):
        for r in csv.DictReader(open(JURIS)):
            juris.setdefault((r["census_id"], r["system"]), []).append(r["board_number"])

    names = {}
    sites = os.path.join(REPO, "notes", "municipal-websites.csv")
    if os.path.exists(sites):
        names = {r["census_id"]: r["csdname"] for r in csv.DictReader(open(sites))}

    out, dropped = [], 0
    if a.batch:
        import glob as _glob
        for f in sorted(_glob.glob(os.path.join(a.batch, "*.html"))):
            cid = os.path.basename(f).replace(".html", "").split("-")[0]
            o, d = harvest_page(f, cid, names.get(cid, ""), juris)
            out.extend(o)
            dropped += d
    else:
        out, dropped = harvest_page(a.page, a.census_id, a.csdname, juris)

    tag = "batch" if a.batch else a.census_id
    dest = a.out or os.path.join(REPO, "data", "raw", "trustees",
                                 f"accordion-{tag}-{date.today().isoformat()}.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    json.dump(out, open(dest, "w"), indent=1)

    nc = sum(len(c["candidates"]) for c in out)
    em = sum(1 for c in out for x in c["candidates"] if x["email"])
    for system in ("public", "catholic"):
        rs = [c for c in out if c["system"] == system]
        if rs:
            print(f"  {system:<9}: {len(rs):>2} contests, "
                  f"{sum(len(c['candidates']) for c in rs):>3} candidates, "
                  f"boards={sorted({c['board_number'] for c in rs})}")
    print(f"total: {len(out)} contests from "
          f"{len({c['census_id'] for c in out})} municipalities, {nc} candidates, "
          f"{em} with email ({100 * em // max(nc, 1)}%)")
    print(f"dropped withdrawn nominations: {dropped}")
    print(f"wrote {os.path.relpath(dest, REPO)}")


if __name__ == "__main__":
    main()
