# places2leads

Turn the free [Foursquare Open Source Places](https://docs.foursquare.com/data-products/docs/places-os-data-schema) dataset into clean, verified contact lists of local businesses, in minutes and without downloading tens of gigabytes.

```
places2leads extract --country US --categories hvac,pest-control --out data/us
places2leads build   --parts data/us --out us_leads.csv --enrich
```

Built for small agencies, researchers and founders who need an honest, reproducible way to find local businesses by category, instead of buying stale lists.

## What it does

1. **Extract.** Reads only the columns and row groups it needs from the remote Parquet dataset with DuckDB over HTTPS. It skips files that can't contain the requested country by checking Parquet column statistics first. Runs are resumable: if you hit a time limit, run the same command again.
2. **Enrich (optional).** For businesses with a website but no email in the dataset, it looks for a public contact email on the business's own homepage and up to three contact or about pages. It respects `robots.txt`, identifies itself, caps page size and caches every result.
3. **Validate.** Cleans and filters emails without sending anything:
   - syntax and junk filtering (image file names, placeholders, tracking services)
   - drops role addresses you shouldn't contact (postmaster, careers, billing)
   - removes chains (many listings sharing one email domain)
   - de-duplicates
   - checks the domain has working MX records
   - only accepts website-found emails on the site's own domain (or a common free provider)
4. **Export.** One CSV: name, email, website, city, region, and where the email came from.

## Example results

From our own runs in November 2026 on the 2025-02-06 release:

| Country | Categories | Businesses with a usable email |
| --- | --- | --- |
| US | 10 home-service, pet, fitness and auto categories | about 220,000 |
| Australia | same 10 categories, with website enrichment (about 20,000 sites checked) | about 13,000 |
| New Zealand | same 10 categories, with website enrichment | about 950 |

Coverage varies a lot by country: the dataset is rich for the US and much thinner elsewhere. Always verify a list before using it; data ages.

## Install

```
git clone https://github.com/devnirwal01/places2leads
cd places2leads
pip install -e .
```

Python 3.10+. Dependencies: `duckdb`, `requests`, `dnspython`.

## Usage

### Category presets

`hvac`, `pest-control`, `landscaping`, `cleaning`, `auto-repair`, `vets`, `pet-grooming`, `fitness-studios`, `martial-arts`. Combine with commas. Or pass any regular expression over Foursquare category labels with `--regex`, for example `--regex "Bakery|Coffee Shop"`.

### Extract

```
places2leads extract --country AU --categories landscaping --out data/au --time-budget 600
```

| Option | Meaning |
| --- | --- |
| `--country` | ISO country code as used in the dataset (US, AU, NZ, GB, ...) |
| `--release` | Dataset release folder (default `2025-02-06`) |
| `--base` | Dataset base URL, if you use another mirror or a newer release |
| `--time-budget` | Stop after N seconds; run again to resume |

### Build

```
places2leads build --parts data/au --out au_leads.csv --enrich --cache data/sites.json \
  --user-agent "my-research-bot (+https://example.com/contact)" --exclude "franchise name|another chain"
```

| Option | Meaning |
| --- | --- |
| `--enrich` | Look for missing emails on business websites |
| `--cache` | JSON cache of website results (resumable) |
| `--user-agent` | Identify yourself with a contact URL. Please set this. |
| `--workers` | Parallel website checks (default 32) |
| `--exclude` | Regex of business names to drop, such as known chains |
| `--max-per-domain` | Treat an email domain shared by more listings than this as a chain (default 5) |
| `--no-mx` | Skip the MX record check |

## Responsible use

This tool only collects information businesses publish about themselves: listings in an openly licensed dataset and contact details on their own public websites. How you use the results is your responsibility.

- **Follow the law where you send.** Examples: CAN-SPAM in the US (honest headers, a postal address, a working opt-out honoured promptly); the Spam Act 2003 in Australia and the Unsolicited Electronic Messages Act 2007 in New Zealand (consent rules apply, including conditions for publicly listed business addresses); UK PECR and UK GDPR. This is not legal advice.
- **Contact businesses, not individuals,** about things relevant to their business.
- **Verify before sending** and keep bounce rates low. Remove anyone who asks.
- **Be a polite crawler.** Keep `robots.txt` respect on, set a real User-Agent with contact details, and keep concurrency reasonable.
- **Respect the data licence.** Foursquare OS Places is Apache 2.0; keep its attribution when you share derived data.

## Data source and licence

- Data: Foursquare Open Source Places, Apache 2.0. Newer releases may be published behind a free sign-up on Hugging Face; point `--base` and `--release` at any mirror you have access to.
- Code: MIT licence (see LICENSE).

## Development

```
pip install -e ".[dev]"
pytest
```

Contributions welcome: more category presets, other open data sources (OpenStreetMap, national business registers), better email extraction, and tests.

## History

Built in November 2026 while preparing outreach lists for a small marketing business, then cleaned up and open-sourced.
