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

LABELS COME FROM TWO PLACES, tried in order: an accordion toggle button, and any heading
element (h1-h6, summary, caption, th spanning the table, or a bolded paragraph) that
precedes a table. Whichever is found, it is combined with the nearest preceding section
heading that mentions a trustee - see BOARD RESOLUTION.

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
CELL_EMPTY = re.compile(r"^-?$")


def txt(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


# A heading that introduces a run of trustee accordions. Kept broad - the point is only to
# supply the words the button omits.
SECTION_HEAD = re.compile(
    r"(?is)<(?:p|h[1-6]|strong|legend)[^>]*>((?:(?!</?(?:p|h[1-6]|strong|legend)).){0,200}?"
    r"(?:trustee|school board)(?:(?!</?(?:p|h[1-6]|strong|legend)).){0,200}?)</(?:p|h[1-6]|strong|legend)>")


# Anything that can carry a contest label immediately above its table.
LABEL_EL = re.compile(
    r'(?is)<button[^>]*accordion[^>]*>(.*?)</button>'
    r'|<(?:h[1-6]|summary|caption|legend)[^>]*>(.*?)</(?:h[1-6]|summary|caption|legend)>'
    r'|<p[^>]*>\s*<strong[^>]*>(.*?)</strong>\s*</p>')


def sections(doc):
    """Yield (label with context, bare label, table html) for each labelled table.

    The section heading matters as much as the label: see BOARD RESOLUTION.
    """
    heads = [(m.start(), txt(m.group(1))) for m in SECTION_HEAD.finditer(doc)]
    labels = [(m.start(), m.end(), txt(next(g for g in m.groups() if g is not None)))
              for m in LABEL_EL.finditer(doc)
              if any(g is not None for g in m.groups())]
    tables = list(re.finditer(r"(?is)<table.*?</table>", doc))

    for t in tables:
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
        yield (f"{head} - {label}" if head else label), label, t.group(0)


EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Cloudflare's placeholder, and anything else that is a label rather than an address.
BAD_EMAIL = re.compile(r"email\s*protected|^\s*$", re.I)
# Where a page crams the whole record into the name cell, the name ends here.
RECORD_NOISE = re.compile(
    r"\s*(nomination\s+filed|qualifying\s+address|date\s+filed|e-?mail|telephone|phone|"
    r"website|please\s+note|the\s+above\s+candidate)\b.*$", re.I)
# A header row the header detector did not catch, or boilerplate.
NOT_A_CANDIDATE = re.compile(
    r"^(trustee\s+)?(candidate\s*name|name|date|office|ward|position|contact|information|"
    r"school\s+board.*|the\s+.*)$"
    r"|by\s+virtue\s+of\s+office", re.I)
# A plausible person name after trimming: at least two words, not absurdly long.
LOOKS_LIKE_NAME = re.compile(r"^[^\d]{3,60}$")
PHONE_RX = re.compile(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}")
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


def harvest_page(path, census_id, csdname, juris):
    doc = open(path, encoding="utf-8", errors="replace").read()
    out, dropped = [], 0
    for label, button_label, table in sections(doc):
        board, system, reason = classify(label)
        if board is None:
            continue
        if str(board).startswith("UNRESOLVED") and system:
            known = juris.get((census_id, system), [])
            if len(known) == 1:
                board, reason = known[0], "resolved-from-jurisdictions"

        header, idx, cands = None, {}, []
        for cells, raw_row in rows(table):
            if header is None and re.match(r"(?i)\s*name", cells[0] or ""):
                header = [c.lower() for c in cells]
                idx = col_index(header)
                continue
            name = cells[0]
            if not name or CELL_EMPTY.match(name):
                continue
            if WITHDRAWN.search(name):
                dropped += 1
                continue
            def val(k):
                i = idx.get(k)
                if i is None or i >= len(cells):
                    return ""
                v = cells[i]
                return "" if CELL_EMPTY.match(v or "") else v
            email, phone, site = val("email"), val("phone"), val("website")
            # Row-scan fallback for pages that put contact inline; see the docstring.
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
            # The name cell sometimes carries the whole record; cut it back to the name.
            name = EMAIL_RX.sub("", name)
            name = RECORD_NOISE.sub("", name).strip(" |,-\u2013\u2014")
            if (not name or NOT_A_CANDIDATE.match(name)
                    or not LOOKS_LIKE_NAME.match(name)
                    or len(name.split()) < 2):
                continue
            cands.append({"name_raw": name, "acclaimed": False,
                          "email": email, "phone": phone,
                          "address": val("address"),
                          "links": [site] if site else []})
        if not cands:
            continue
        out.append({"census_id": census_id, "csdname": csdname, "county_mun": "",
                    "office": button_label, "office_context": label,
                    "board_number": board, "system": system,
                    "classify_reason": reason, "empty_notice": False,
                    "candidates": cands})
    return out, dropped


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
