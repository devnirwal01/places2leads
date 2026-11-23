"""Extract local businesses from the Foursquare Open Source Places dataset.

The dataset is published under the Apache 2.0 licence. It is large (tens of GB),
so we never download it whole: DuckDB reads only the columns and row groups we
need, straight over HTTPS, and we skip files whose bounding box or country
statistics can't contain the requested country.
"""
from __future__ import annotations

import os
import re
import time
from typing import Iterable

import duckdb

DEFAULT_BASE = "https://data.source.coop/fused/fsq-os-places"

COLUMNS = (
    "fsq_place_id, name, website, email, tel, address, locality, region, postcode, "
    "country, latitude, longitude, fsq_category_labels, date_closed"
)


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs; SET enable_progress_bar=false;")
    return con


def list_release_files(release: str, base: str = DEFAULT_BASE) -> list[str]:
    """Return the parquet file URLs for a release (e.g. '2025-02-06')."""
    import urllib.request

    keys, marker = [], ""
    while True:
        url = f"{base}/?marker={marker}"
        xml = urllib.request.urlopen(url, timeout=60).read().decode()
        found = re.findall(r"<Key>([^<]+)</Key>", xml)
        keys += found
        if "<IsTruncated>true" in xml and found:
            marker = found[-1]
        else:
            break
    prefix = base.rstrip("/").split("/")[-1] + f"/{release}/places/"
    root = base.rsplit("/", 1)[0]
    return [f"{root}/{k}" for k in keys if k.startswith(prefix) and k.endswith(".parquet")]


def files_for_country(con, files: list[str], country: str) -> list[str]:
    """Keep only files whose country column statistics can include `country`."""
    lst = "[" + ",".join(f"'{f}'" for f in files) + "]"
    rows = con.sql(
        f"""select file_name, min(stats_min_value), max(stats_max_value)
            from parquet_metadata({lst}) where path_in_schema='country' group by 1"""
    ).fetchall()
    return sorted(f for f, mn, mx in rows if mn and mx and mn <= country <= mx)


def extract(
    country: str,
    category_pattern: str,
    out_dir: str,
    release: str = "2025-02-06",
    base: str = DEFAULT_BASE,
    time_budget_s: float | None = None,
) -> list[str]:
    """Write one parquet part per source file with matching open businesses.

    Resumable: parts that already exist are skipped, so you can re-run after a
    timeout. `category_pattern` is a regular expression matched against the
    joined Foursquare category labels, e.g. 'Heating, Ventilating|Pest Control'.
    """
    os.makedirs(out_dir, exist_ok=True)
    con = connect()
    files = files_for_country(con, list_release_files(release, base), country)
    pattern = category_pattern.replace("'", "''")
    start, written = time.time(), []
    for i, f in enumerate(files):
        part = os.path.join(out_dir, f"part_{i:04d}.parquet")
        if os.path.exists(part):
            written.append(part)
            continue
        if time_budget_s and time.time() - start > time_budget_s:
            break
        tmp = part + ".tmp"
        con.sql(
            f"""copy (select {COLUMNS} from '{f}'
                      where country='{country}' and date_closed is null
                        and regexp_matches(array_to_string(fsq_category_labels,'|'), '{pattern}'))
                to '{tmp}' (format parquet)"""
        )
        os.replace(tmp, part)  # only complete parts are kept
        written.append(part)
    remaining = len(files) - len(written)
    if remaining:
        print(f"time budget reached: {remaining} of {len(files)} files left, run again to resume")
    return written


def load(parts: Iterable[str]):
    con = duckdb.connect()
    parts = list(parts)
    if not parts:
        return []
    lst = "[" + ",".join(f"'{p}'" for p in parts) + "]"
    return con.sql(f"select * from read_parquet({lst})").fetchall()
