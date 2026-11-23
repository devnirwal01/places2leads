#!/usr/bin/env bash
# Example: HVAC and pest control businesses in New Zealand, with website enrichment.
set -euo pipefail
places2leads extract --country NZ --categories hvac,pest-control --out data/nz --time-budget 600
places2leads build --parts data/nz --out nz_leads.csv --enrich --cache data/sites.json \
  --user-agent "places2leads example (+https://github.com/devnirwal01/places2leads)"
