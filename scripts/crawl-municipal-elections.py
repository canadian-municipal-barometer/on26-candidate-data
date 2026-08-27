#!/usr/bin/env python3
"""Find and fetch each municipality's 2026 candidate list, ready for hand collection.

Usage: python3 scripts/crawl-municipal-elections.py [--cache DIR] [--limit N] [--workers N]

Resolves the repo root from its own path. Only dependency is curl.

WHAT THIS IS FOR. There are 414 Ontario municipalities that run a ballot and no published
index of where each one puts its candidate list. This walks from each municipality's
official website to the page that carries it, saves that page, and records what it found.
It does NOT decide who the candidates are - that stays hand-collected in
data/raw/trustees/by-zone/. What it produces is a work queue with the reading already done:
a URL, a saved copy, and a first read of which boards appear on it.

HOW IT FINDS THE PAGE. Municipal sites share no common structure, so the crawl is a scored
walk rather than a set of guessed paths. From the homepage it scores every link on its text
and href, follows the best few, and scores the pages they lead to. A page scores as a
candidate list if it names a school board or says "certified"/"acclaimed" next to a
trustee; that is a deliberately narrow test, because a page merely mentioning the election
is not the list.

Politeness. One request at a time per host, a delay between them, and a short timeout.
Workers run across DIFFERENT municipalities, so no single site sees concurrent requests.

ROBUSTNESS. Two things this learned the hard way. Municipal pages are not all UTF-8 - some
are cp1252, some are mislabelled - so output is captured as BYTES and decoded with
replacement rather than letting subprocess decode strictly and raise. And one municipality
must never end the run: crawl() catches everything and returns a row saying what failed, so
a single bad site costs one row instead of the other 372.

Inputs
  notes/municipal-websites.csv    census_id -> official website (built by
                                  scripts/build-municipal-websites.py)
  notes/voterview-municipalities.csv  skipped: already covered by the VoterView harvest
  data/boards/boards.csv          the 60 board names to look for

Output
  notes/municipal-election-pages.csv
      census_id, csdname, website, election_url, status, boards_found, n_emails, saved_as
      status is one of: found | no-list-found | unreachable | no-website | error
"""
import csv
import html
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trustee_boards import BOARDS  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITES = os.path.join(REPO, "notes", "municipal-websites.csv")
SKIP = os.path.join(REPO, "notes", "voterview-municipalities.csv")
DEST = os.path.join(REPO, "notes", "municipal-election-pages.csv")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
TIMEOUT = "25"
DELAY = 0.6           # between requests to the same municipality
MAX_FOLLOW = 4        # links followed from the homepage
MAX_DEPTH = 2

BALLOT_TIERS = ("Lower Tier", "Single Tier")

# Link text / href scoring. A link has to look like it leads to the list itself, not to
# general election information, so "candidate" and "who is running" outrank "election".
LINK_SCORES = [
    (re.compile(r"certified.{0,20}candidate|candidate.{0,10}list|list.{0,10}candidate", re.I), 12),
    (re.compile(r"who.{0,5}is.{0,5}running|whos.?running", re.I), 12),
    (re.compile(r"registered candidate|candidates? and third part", re.I), 10),
    (re.compile(r"\bcandidate", re.I), 7),
    (re.compile(r"\bnomination", re.I), 4),
    (re.compile(r"2026.{0,20}election|election.{0,20}2026", re.I), 4),
    (re.compile(r"municipal election|school board election", re.I), 3),
    (re.compile(r"\belection", re.I), 2),
    (re.compile(r"\bvote|voter", re.I), 1),
]
SKIP_LINK = re.compile(r"\.(pdf|jpg|jpeg|png|gif|docx?|xlsx?|zip)$|mailto:|tel:|"
                       r"facebook\.com|twitter\.com|x\.com|instagram|youtube|linkedin", re.I)

BOARD_NAMES = [(n, re.compile(re.escape(v[1]), re.I)) for n, v in BOARDS.items()]
TRUSTEE = re.compile(r"trustee", re.I)
CERTIFIED = re.compile(r"certified|acclaimed|declared elected", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w{2,}")


def get(url):
    """Fetch a page as text. Never raises: a site that cannot be read is an empty string."""
    try:
        r = subprocess.run(["curl", "-sSL", "-A", UA, "--max-time", TIMEOUT,
                            "--compressed", url], capture_output=True)
    except Exception:
        return ""
    if r.returncode != 0:
        return ""
    # Not every municipal site is UTF-8, and some mislabel their encoding. Decode with
    # replacement rather than strictly: this is scored on keywords, so a mangled accent
    # costs nothing and a raised exception costs the whole crawl.
    return r.stdout.decode("utf-8", errors="replace")


def visible(doc):
    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", doc)
    t = re.sub(r"(?is)<br\s*/?>", "\n", t)
    t = re.sub(r"(?is)</(p|div|li|tr|h\d|td|a|strong|span)>", "\n", t)
    return html.unescape(re.sub(r"<[^>]+>", " ", t))


def links(doc, base):
    out = []
    for m in re.finditer(r'(?is)<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', doc):
        href, text = m.group(1).strip(), re.sub(r"\s+", " ",
                                                html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip()
        if not href or href.startswith("#") or SKIP_LINK.search(href):
            continue
        url = urljoin(base, href)
        if urlparse(url).netloc != urlparse(base).netloc:
            continue
        score = sum(w for rx, w in LINK_SCORES if rx.search(text) or rx.search(href))
        if score:
            out.append((score, url, text[:70]))
    # best first, de-duplicated on URL
    seen, ranked = set(), []
    for score, url, text in sorted(out, key=lambda x: -x[0]):
        if url in seen:
            continue
        seen.add(url)
        ranked.append((score, url, text))
    return ranked


def looks_like_list(doc):
    """A page is the candidate list if a board is named, or a trustee is called certified."""
    text = visible(doc)
    found = [n for n, rx in BOARD_NAMES if rx.search(text)]
    if found:
        return found, text
    if TRUSTEE.search(text) and CERTIFIED.search(text):
        return [], text
    return None, text


def crawl(row, cache):
    """Never raises - see ROBUSTNESS in the module docstring."""
    try:
        return _crawl(row, cache)
    except Exception as exc:
        return {"census_id": row["census_id"], "csdname": row["csdname"],
                "website": row["website"], "election_url": "", "status": "error",
                "boards_found": "", "n_emails": 0, "saved_as": "",
                "error": f"{type(exc).__name__}: {exc}"[:120]}


def _crawl(row, cache):
    cid, name, site = row["census_id"], row["csdname"], row["website"]
    res = {"census_id": cid, "csdname": name, "website": site, "election_url": "",
           "status": "no-website", "boards_found": "", "n_emails": 0, "saved_as": "",
           "error": ""}
    if not site:
        return res
    home = get(site)
    time.sleep(DELAY)
    if not home:
        res["status"] = "unreachable"
        return res

    seen = {site}
    frontier = links(home, site)[:MAX_FOLLOW]
    best = None
    for depth in range(MAX_DEPTH):
        nxt = []
        for score, url, text in frontier:
            if url in seen:
                continue
            seen.add(url)
            doc = get(url)
            time.sleep(DELAY)
            if not doc:
                continue
            found, text_body = looks_like_list(doc)
            if found is not None:
                best = (url, found, doc, text_body)
                break
            if depth + 1 < MAX_DEPTH:
                nxt.extend(links(doc, url)[:2])
        if best:
            break
        frontier = sorted(nxt, key=lambda x: -x[0])[:MAX_FOLLOW]

    if not best:
        res["status"] = "no-list-found"
        return res

    url, found, doc, text_body = best
    res.update(status="found", election_url=url,
               boards_found="|".join(sorted(found)),
               n_emails=len(set(EMAIL.findall(text_body))))
    if cache:
        os.makedirs(cache, exist_ok=True)
        path = os.path.join(cache, f"{cid}.html")
        open(path, "w", encoding="utf-8").write(doc)
        res["saved_as"] = os.path.basename(path)
    return res


def main():
    args = sys.argv[1:]
    cache = args[args.index("--cache") + 1] if "--cache" in args else None
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 4

    skip = {r["census_id"] for r in csv.DictReader(open(SKIP))} if os.path.exists(SKIP) else set()
    rows = [r for r in csv.DictReader(open(SITES))
            if r["tier"] in BALLOT_TIERS and r["census_id"] not in skip]
    if limit:
        rows = rows[:limit]
    print(f"crawling {len(rows)} municipalities ({len(skip)} already on VoterView), "
          f"{workers} workers", flush=True)

    out = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, res in enumerate(ex.map(lambda r: crawl(r, cache), rows), 1):
            out.append(res)
            print(f"{i:>3}/{len(rows)} {res['census_id']} {res['csdname'][:26]:<27} "
                  f"{res['status']:<14} boards={res['boards_found'][:40]:<41} "
                  f"emails={res['n_emails']}", flush=True)

    out.sort(key=lambda r: r["csdname"])
    with open(DEST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    from collections import Counter
    c = Counter(r["status"] for r in out)
    print(f"\n{dict(c)}")
    print(f"pages naming >=1 board : {sum(1 for r in out if r['boards_found'])}")
    print(f"pages carrying emails  : {sum(1 for r in out if r['n_emails'])}")
    print(f"wrote {os.path.relpath(DEST, REPO)}")


if __name__ == "__main__":
    main()
