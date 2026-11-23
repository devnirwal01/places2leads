"""Clean and validate business emails without sending anything.

Checks: syntax, junk patterns (image names, placeholders, tracking services),
role addresses you shouldn't contact, chain detection by shared domains,
de-duplication, MX records, and whether the email matches the website domain.
"""
from __future__ import annotations

import concurrent.futures as cf
import re
import urllib.parse
from collections import Counter

import dns.resolver

EMAIL_OK = re.compile(r"^[a-z0-9._%+'-]+@[a-z0-9.-]+\.[a-z]{2,}$")
JUNK = re.compile(
    r"example\.|domain\.com|yourdomain|email\.com|sentry|wixpress|godaddy|cloudflare|"
    r"\.(png|jpe?g|gif|webp|svg|css|js)$|@2x|^(test|user|name|abc)@|noreply|no-reply|donotreply",
    re.I,
)
ROLE_SKIP = re.compile(r"^(postmaster|abuse|webmaster|privacy|careers|jobs|hr|billing|invoices?)@")
FREE_PROVIDERS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com", "live.com",
    "msn.com", "me.com", "comcast.net", "att.net", "sbcglobal.net", "verizon.net", "bellsouth.net",
    "charter.net", "cox.net", "ymail.com", "earthlink.net", "protonmail.com", "mail.com",
    "bigpond.com", "optusnet.com.au", "xtra.co.nz", "btinternet.com",
}


def clean_email(raw: str | None) -> str | None:
    if not raw:
        return None
    e = raw.strip().lower().replace("mailto:", "").split("?")[0].split(",")[0].split(";")[0].strip()
    if not EMAIL_OK.match(e) or JUNK.search(e) or ROLE_SKIP.match(e):
        return None
    return e


def domain_of(url: str | None) -> str:
    if not url:
        return ""
    if not url.startswith("http"):
        url = "http://" + url
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.").split(":")[0]


def matches_website(email: str, website: str | None) -> bool:
    d = domain_of(website)
    return bool(d) and (email.split("@")[1] == d or email.split("@")[1].endswith("." + d))


def drop_chains(records: list[dict], max_per_domain: int = 5) -> list[dict]:
    """Remove records whose (non-free) email domain is shared by many listings: usually a chain."""
    counts = Counter(r["email"].split("@")[1] for r in records)
    return [r for r in records
            if r["email"].split("@")[1] in FREE_PROVIDERS or counts[r["email"].split("@")[1]] <= max_per_domain]


def dedupe(records: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in records:
        if r["email"] not in seen:
            seen.add(r["email"])
            out.append(r)
    return out


def mx_check(domains: set[str], workers: int = 64) -> dict[str, bool]:
    res = dns.resolver.Resolver()
    res.lifetime = res.timeout = 4

    def one(d):
        try:
            res.resolve(d, "MX")
            return d, True
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            return d, False
        except Exception:
            return d, True  # temporary DNS error: don't throw the lead away

    with cf.ThreadPoolExecutor(workers) as pool:
        return dict(pool.map(one, domains))
