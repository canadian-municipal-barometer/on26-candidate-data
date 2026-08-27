#!/usr/bin/env python3
"""Pull the trustee part of each crawled candidate list into a reviewable work queue.

Usage: python3 scripts/extract-trustee-sections.py --cache DIR [--out FILE]

Resolves the repo root from its own path. No dependencies.

WHAT THIS IS AND IS NOT. Municipal candidate pages share no structure - some are tables,
some accordions, some a flat run of headings - so there is no parser that reads all of them
correctly. This does not pretend otherwise. It finds the part of each page that is about
trustees, extracts what it can, and says how confident it is, so that hand collection into
data/raw/trustees/by-zone/ starts from a page's trustee section rather than from its
homepage. The source of truth stays hand-collected; this is the reading, not the ruling.

HOW THE SECTION IS FOUND. A trustee section starts at a line naming one of the 60 boards or
containing "trustee", and runs until a line that clearly belongs to a different office
(mayor, councillor, deputy mayor, regional councillor) or until the boards run out. Council
races are the thing most likely to be swept in, so the office words that end a section are
matched before anything else.

TWO RULES KEEP NAVIGATION OUT, and both were added after the first run swallowed a site's
menu as candidate names ("Green Bin Registration", "Toggle Menu Elections"):

  A section is only emitted if its heading identifies a BOARD. A heading that merely says
  "School Board Trustees:" starts a run with no end marker on a page whose trustee list is
  rendered elsewhere, and it will happily absorb the footer.

  A section body is capped at MAX_SECTION_LINES. A real trustee contest is a heading and a
  handful of names; anything an order of magnitude longer is page furniture, not a ballot.

A THIRD RULE WORKS ACROSS PAGES. "Voting Process" and "Financial Statements" look exactly
like names to any single-page rule, and no word list catches all of them. But they differ
from real names in one way that is easy to measure: menu labels recur across many
municipalities' websites, and a candidate does not. So after every page is read, any
name-like line appearing in more than NAV_DOC_FREQ municipalities is dropped as furniture.
The threshold is well above the number of municipalities a single English-language trustee
zone spans, and every dropped line is reported so the cut can be audited rather than
trusted.

CONFIDENCE. Reported per municipality, and worth trusting more than the extraction itself:
  high   a board was named AND at least one name-like line was found under it
  medium a trustee section was found but no board name, or names without a board heading
  low    the word trustee appears but nothing parsed cleanly
A "low" is not a failure to hide - it is the queue of pages that need a human.
"""
import csv
import glob
import html
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trustee_boards import BOARDS, classify  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = os.path.join(REPO, "notes", "municipal-election-pages.csv")

BOARD_RX = [(n, re.compile(re.escape(v[1]), re.I)) for n, v in BOARDS.items()]
TRUSTEE = re.compile(r"\btrustee", re.I)
# Offices that end a trustee section. Matched on a line of its own, so a candidate whose
# blurb mentions "council" does not truncate the section.
OTHER_OFFICE = re.compile(
    r"^\s*(mayor|deputy mayor|regional councillor|ward councillor|councillor|"
    r"council member|reeve|deputy reeve)\b[^a-z]*$", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w{2,}")
PHONE = re.compile(r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}")
URL = re.compile(r"https?://[^\s<>\"]+")

# A line that looks like a person's name: two to four capitalised words, no digits, no
# punctuation that a name would not carry. Deliberately strict - a false name is worse than
# a missed one here, because this feeds a queue a human reads.
NAME_LINE = re.compile(
    r"^[A-ZÀ-Ý][\w'’.-]*(?:\s+(?:de|del|van|von|der|da|di|la|le|St\.|Mc|Mac)?[A-ZÀ-Ý][\w'’.-]*){1,3}$")
NOT_NAME = re.compile(
    r"\b(school|board|trustee|ward|district|election|candidate|city|town|township|county|"
    r"municipal|public|catholic|separate|english|french|contact|email|phone|website|"
    r"nomination|acclaimed|certified|address|vote|elected|office|clerk|information|"
    # site furniture that reads like a name: "Living Here", "Green Bin Registration"
    r"toggle|menu|section|registration|newsletter|services|programs|facilities|"
    r"living|about|home|search|skip|apply|report|permits|bylaw|by-law|council meeting|"
    r"agenda|minutes|careers|contact us|news|events|parks|recreation|library|fire|"
    r"water|waste|roads|planning|building|tax|payment|form|policy|plan|notice)\b", re.I)

# A real trustee contest is a heading plus a few names. Past this, the run has escaped into
# the page's own furniture - see the docstring.
MAX_SECTION_LINES = 40

# A name-like line appearing in more municipalities than this is site furniture, not a
# candidate. English public and Catholic trustee zones span a handful of municipalities at
# most, so this is generous; see the docstring.
NAV_DOC_FREQ = 8


def visible_lines(doc):
    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", doc)
    t = re.sub(r"(?is)<br\s*/?>", "\n", t)
    t = re.sub(r"(?is)</(p|div|li|tr|h\d|td|th|a|strong|b|span|option)>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    out = []
    for ln in t.split("\n"):
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            out.append(ln)
    return out


def sections(lines):
    """Yield (board_number|None, heading, [lines]) for each trustee run on the page."""
    i, n = 0, len(lines)
    while i < n:
        board = next((b for b, rx in BOARD_RX if rx.search(lines[i])), None)
        if board or TRUSTEE.search(lines[i]):
            head, body, j = lines[i], [], i + 1
            while j < n:
                if OTHER_OFFICE.match(lines[j]):
                    break
                if any(rx.search(lines[j]) for _, rx in BOARD_RX) or TRUSTEE.search(lines[j]):
                    break
                body.append(lines[j])
                j += 1
            yield board, head, body
            i = j
        else:
            i += 1


def main():
    args = sys.argv[1:]
    if "--cache" not in args:
        sys.exit(__doc__)
    cache = args[args.index("--cache") + 1]
    out_path = (args[args.index("--out") + 1] if "--out" in args
                else os.path.join(REPO, "data", "raw", "trustees",
                                  "municipal-trustee-sections.json"))

    meta = {r["census_id"]: r for r in csv.DictReader(open(PAGES))} if os.path.exists(PAGES) else {}

    out = []
    for p in sorted(glob.glob(os.path.join(cache, "*.html"))):
        cid = os.path.basename(p).replace(".html", "")
        lines = visible_lines(open(p, encoding="utf-8", errors="replace").read())
        found = []
        for board, head, body in sections(lines):
            bn, system, _ = classify(head)
            board_number = board or bn
            # Only a section whose heading identifies a board is trustworthy; see docstring.
            if not board_number or str(board_number).startswith("AMBIGUOUS"):
                continue
            if len(body) > MAX_SECTION_LINES:
                body = body[:MAX_SECTION_LINES]
            names = [ln for ln in body if NAME_LINE.match(ln) and not NOT_NAME.search(ln)]
            if not names:
                continue
            found.append({
                "board_number": board_number,
                "system": system,
                "heading": head,
                "names": names,
                "emails": sorted(set(EMAIL.findall(" ".join(body)))),
                "phones": sorted(set(PHONE.findall(" ".join(body)))),
                "links": sorted(set(URL.findall(" ".join(body))))[:8],
                "section_lines": len(body),
            })
        if not found:
            conf = "low"
        elif any(not str(s["board_number"]).startswith("UNRESOLVED") for s in found):
            conf = "high"
        else:
            conf = "medium"
        m = meta.get(cid, {})
        out.append({"census_id": cid, "csdname": m.get("csdname", ""),
                    "election_url": m.get("election_url", ""),
                    "confidence": conf, "sections": found})

    # Cross-page furniture filter; see NAV_DOC_FREQ.
    doc_freq = {}
    for r in out:
        for nm in {n for sec in r["sections"] for n in sec["names"]}:
            doc_freq[nm] = doc_freq.get(nm, 0) + 1
    furniture = {n for n, k in doc_freq.items() if k > NAV_DOC_FREQ}
    dropped = 0
    for r in out:
        for sec in r["sections"]:
            keep = [n for n in sec["names"] if n not in furniture]
            dropped += len(sec["names"]) - len(keep)
            sec["names"] = keep
        r["sections"] = [sec for sec in r["sections"] if sec["names"]]
        if not r["sections"]:
            r["confidence"] = "low"
        elif any(not str(sec["board_number"]).startswith("UNRESOLVED")
                 for sec in r["sections"]):
            r["confidence"] = "high"
        else:
            r["confidence"] = "medium"

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=1)

    print(f"furniture filter: dropped {dropped} lines seen in >{NAV_DOC_FREQ} municipalities")
    for n in sorted(furniture, key=lambda x: -doc_freq[x])[:12]:
        print(f"    {doc_freq[n]:>3}x  {n}")

    from collections import Counter
    c = Counter(r["confidence"] for r in out)
    names = sum(len(s["names"]) for r in out for s in r["sections"])
    mails = sum(len(s["emails"]) for r in out for s in r["sections"])
    print(f"pages read      : {len(out)}   confidence: {dict(c)}")
    print(f"trustee sections: {sum(len(r['sections']) for r in out)}")
    print(f"name-like lines : {names}")
    print(f"emails in them  : {mails}")
    print(f"wrote {os.path.relpath(out_path, REPO)}")


if __name__ == "__main__":
    main()
