"""Find a public contact email on a business's own website.

Polite by design:
- respects robots.txt for every site
- identifies itself with a clear User-Agent (set your own contact URL)
- fetches at most the homepage plus up to 3 contact/about pages
- caps page size and uses short timeouts
- results are cached so sites are never crawled twice
"""
from __future__ import annotations

import concurrent.futures as cf
import html
import json
import os
import re
import time
import urllib.parse
import urllib.robotparser

import requests

requests.packages.urllib3.disable_warnings()  # some small-business sites have broken TLS

DEFAULT_UA = "places2leads/0.1 (+https://github.com/devnirwal01/places2leads)"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
LINK_HINTS = re.compile(r"contact|about|get-in-touch|enquir|kontakt|contacto", re.I)
MAX_BYTES = 500_000


def _robots_ok(url: str, ua: str, cache: dict) -> bool:
    parts = urllib.parse.urlparse(url)
    root = f"{parts.scheme}://{parts.netloc}"
    if root not in cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(root + "/robots.txt", headers={"User-Agent": ua}, timeout=5, verify=False)
            rp.parse(r.text.splitlines() if r.status_code < 400 else [])
        except Exception:
            rp.parse([])
        cache[root] = rp
    return cache[root].can_fetch(ua, url)


def _get(url: str, ua: str) -> tuple[str | None, str]:
    try:
        r = requests.get(url, headers={"User-Agent": ua, "Accept": "text/html"}, timeout=(5, 8),
                         verify=False, allow_redirects=True, stream=True)
        if r.status_code < 400 and "text" in r.headers.get("content-type", "text"):
            body = b""
            for chunk in r.iter_content(65536):
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            r.close()
            return r.url, body.decode(r.encoding or "utf-8", "ignore")
        r.close()
    except Exception:
        pass
    return None, ""


def emails_in(text: str) -> list[str]:
    text = html.unescape(urllib.parse.unquote(text.replace("[at]", "@").replace("(at)", "@")))
    found = []
    for m in EMAIL_RE.findall(text):
        e = m.strip(".").lower()
        if e not in found and len(e) <= 60:
            found.append(e)
    return found


def _contact_links(base: str, text: str) -> list[str]:
    out = []
    host = urllib.parse.urlparse(base).netloc
    for href in re.findall(r'href=["\']([^"\'#]+)["\']', text, re.I):
        if LINK_HINTS.search(href) and not href.startswith(("mailto:", "tel:")):
            u = urllib.parse.urljoin(base, href)
            if urllib.parse.urlparse(u).netloc == host and u not in out:
                out.append(u)
    return out[:3]


def check_site(website: str, ua: str = DEFAULT_UA, robots_cache: dict | None = None) -> dict:
    """Return {'reachable': bool, 'emails': [...], 'final_url': str|None}."""
    robots_cache = robots_cache if robots_cache is not None else {}
    url = website.strip()
    if not url.startswith("http"):
        url = "http://" + url
    if not _robots_ok(url, ua, robots_cache):
        return {"reachable": None, "emails": [], "final_url": None, "skipped": "robots.txt"}
    final, text = _get(url, ua)
    emails = emails_in(text) if text else []
    if final and not emails:
        for link in _contact_links(final, text):
            if not _robots_ok(link, ua, robots_cache):
                continue
            _, t2 = _get(link, ua)
            emails = emails_in(t2)
            if emails:
                break
    if final:  # put addresses on the site's own domain first
        dom = urllib.parse.urlparse(final).netloc.lower().removeprefix("www.")
        emails.sort(key=lambda e: 0 if e.split("@")[1].endswith(dom) else 1)
    return {"reachable": bool(final), "emails": emails[:3], "final_url": final}


def enrich(websites: list[str], cache_path: str, ua: str = DEFAULT_UA, workers: int = 32,
           time_budget_s: float | None = None) -> dict:
    """Check many websites in parallel with a resumable JSON cache keyed by website."""
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    todo = [w for w in dict.fromkeys(websites) if w and w not in cache]
    robots: dict = {}
    start = time.time()
    with cf.ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(check_site, w, ua, robots): w for w in todo}
        try:
            for fut in cf.as_completed(futures, timeout=time_budget_s):
                cache[futures[fut]] = fut.result()
        except cf.TimeoutError:
            pass  # unfinished sites stay uncached and are retried next run
    with open(cache_path, "w") as f:
        json.dump(cache, f)
    return cache
