"""
AFL-CIO State and Regional Sites ingestor.
Target: any hostname ending in aflcio.org (e.g. miaflcio.org, nysaflcio.org)

These 50+ sites are custom WordPress/HTML builds with no shared template.
Strategy:
  - Derive source_board from the subdomain/domain (e.g. miaflcio.org → AFL-CIO (MI))
  - Delegate all actual extraction to generic.py
  - Accept lower confidence (state sites are irregular)
"""
import re
from urllib.parse import urlparse

from pipeline.ingestors import generic

BOARD_KEY = "aflcio_state"

# Map domain prefixes to state abbreviations
_DOMAIN_STATE_MAP = {
    "miaflcio": "MI",
    "mi.aflcio": "MI",
    "nysaflcio": "NY",
    "ny.aflcio": "NY",
    "calaborcouncil": "CA",
    "ca.aflcio": "CA",
    "ilaflcio": "IL",
    "il.aflcio": "IL",
    "txaflcio": "TX",
    "tx.aflcio": "TX",
    "flaflcio": "FL",
    "fl.aflcio": "FL",
    "ohioaflcio": "OH",
    "oh.aflcio": "OH",
    "gaaflcio": "GA",
    "ga.aflcio": "GA",
    "waaflcio": "WA",
    "wa.aflcio": "WA",
    "oraflcio": "OR",
    "or.aflcio": "OR",
    "mnaflcio": "MN",
    "mn.aflcio": "MN",
    "wiaflcio": "WI",
    "wi.aflcio": "WI",
    "paaflcio": "PA",
    "pa.aflcio": "PA",
    "azaflcio": "AZ",
    "az.aflcio": "AZ",
    "ncaflcio": "NC",
    "nc.aflcio": "NC",
    "nevaflcio": "NV",
    "nv.aflcio": "NV",
}


def _derive_source_board(url):
    """
    Derive a human-readable source_board name from the domain.
    'miaflcio.org' → 'AFL-CIO (MI)'
    'nysaflcio.org' → 'AFL-CIO (NY)'
    Unknown → 'AFL-CIO Affiliate'
    """
    hostname = urlparse(url).netloc.lower().lstrip("www.")
    # Strip .org suffix
    stem = re.sub(r'\.org$', '', hostname)

    # Direct lookup
    if stem in _DOMAIN_STATE_MAP:
        state = _DOMAIN_STATE_MAP[stem]
        return f"AFL-CIO ({state})"

    # Partial match: check if stem starts with any known prefix
    for prefix, state in _DOMAIN_STATE_MAP.items():
        if stem.startswith(prefix.replace(".", "")) or stem.endswith("aflcio"):
            # Try to extract 2-letter state from beginning of stem
            m = re.match(r'^([a-z]{2,3})aflcio', stem)
            if m:
                abbr = m.group(1).upper()
                return f"AFL-CIO ({abbr})"

    return "AFL-CIO Affiliate"


def ingest(url):
    """
    Ingest from a state AFL-CIO URL.
    Sets source_board from domain, delegates extraction to generic.
    """
    source_board = _derive_source_board(url)
    print(f"INFO [aflcio_state]: source_board={source_board!r}, ingesting {url}")

    jobs = generic.ingest(url)

    for job in jobs:
        job["source_board"] = source_board

    return jobs
