"""Command line: places2leads extract | build

Typical run:
  places2leads extract --country US --categories hvac,pest-control --out data/us
  places2leads build   --parts data/us --out leads_us.csv --enrich --cache data/sites.json
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys

from . import enrich as enrich_mod
from . import extract as extract_mod
from . import validate as v

PRESETS = {
    "hvac": "Heating, Ventilating and Air Conditioning",
    "pest-control": "Pest Control",
    "landscaping": "Landscaper and Gardener",
    "cleaning": "Professional Cleaning",
    "auto-repair": "Automotive Repair|Oil Change",
    "vets": "Veterinarian",
    "pet-grooming": "Pet Grooming",
    "fitness-studios": "Yoga Studio|Pilates Studio|Cycle Studio",
    "martial-arts": "Martial Arts",
}


def cmd_extract(a):
    pattern = "|".join(PRESETS.get(c, c) for c in a.categories.split(",")) if not a.regex else a.regex
    parts = extract_mod.extract(a.country, pattern, a.out, release=a.release, base=a.base,
                                time_budget_s=a.time_budget)
    print(f"{len(parts)} parquet parts ready in {a.out}")


def cmd_build(a):
    parts = sorted(glob.glob(os.path.join(a.parts, "part_*.parquet")))
    rows = extract_mod.load(parts)
    cols = ["fsq_place_id", "name", "website", "email", "tel", "address", "locality", "region",
            "postcode", "country", "latitude", "longitude", "fsq_category_labels", "date_closed"]
    recs = [dict(zip(cols, r)) for r in rows]
    exclude = re.compile(a.exclude, re.I) if a.exclude else None
    if exclude:
        recs = [r for r in recs if not exclude.search(r["name"] or "")]

    if a.enrich:
        need = [r["website"] for r in recs if r["website"] and not r["email"]]
        cache = enrich_mod.enrich(need, a.cache, ua=a.user_agent, workers=a.workers,
                                  time_budget_s=a.time_budget)
        for r in recs:
            if not r["email"] and r["website"] in cache:
                found = [e for e in cache[r["website"]].get("emails", [])
                         if v.matches_website(e, r["website"]) or e.split("@")[1] in v.FREE_PROVIDERS]
                if found:
                    r["email"], r["email_source"] = found[0], "website"

    out = []
    for r in recs:
        e = v.clean_email(r["email"])
        if e and r["name"]:
            out.append({"name": r["name"].strip(), "email": e, "website": r["website"] or "",
                        "city": r["locality"] or "", "region": r["region"] or "",
                        "email_source": r.get("email_source", "dataset")})
    out = v.dedupe(v.drop_chains(out, a.max_per_domain))
    if not a.no_mx:
        ok = v.mx_check({r["email"].split("@")[1] for r in out})
        out = [r for r in out if ok.get(r["email"].split("@")[1], True)]
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "email", "website", "city", "region", "email_source"])
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} leads written to {a.out}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="places2leads", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="pull businesses for a country and categories")
    e.add_argument("--country", required=True, help="ISO code, e.g. US, AU, NZ, GB")
    e.add_argument("--categories", default="hvac", help=f"comma list of presets: {', '.join(PRESETS)}")
    e.add_argument("--regex", help="custom regex over Foursquare category labels (overrides --categories)")
    e.add_argument("--out", required=True)
    e.add_argument("--release", default="2025-02-06")
    e.add_argument("--base", default=extract_mod.DEFAULT_BASE)
    e.add_argument("--time-budget", type=float, help="stop after N seconds; re-run to resume")
    e.set_defaults(func=cmd_extract)

    b = sub.add_parser("build", help="clean, optionally enrich from websites, validate, export CSV")
    b.add_argument("--parts", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--enrich", action="store_true", help="find missing emails on business websites")
    b.add_argument("--cache", default="sites_cache.json")
    b.add_argument("--user-agent", default=enrich_mod.DEFAULT_UA)
    b.add_argument("--workers", type=int, default=32)
    b.add_argument("--time-budget", type=float)
    b.add_argument("--exclude", help="regex of business names to drop (e.g. known chains)")
    b.add_argument("--max-per-domain", type=int, default=5)
    b.add_argument("--no-mx", action="store_true")
    b.set_defaults(func=cmd_build)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    sys.exit(main())
