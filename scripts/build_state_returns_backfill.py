#!/usr/bin/env python3
"""
Targeted state-returns backfill (Agent 5).

Produces data/processed/state_leg_competitiveness_backfill.csv — a drop-in OVERLAY
for data/processed/state_leg_competitiveness.csv (Agent 2's base file). Agent 2 demoted
several whole states to the presidential floor (Tier C) because no clean national
state-leg / gubernatorial county source exists. This script ingests each state's OWN
most-recent cleanly-obtainable statewide (gubernatorial) county returns and emits a
higher-confidence `gubernatorial` row per upgraded county.

Margin convention matches the base file + county_scores.json: margin = (D - R) / total * 100
(positive = Democratic advantage). competitive = |margin| <= 3.

Only counties that were on the presidential floor in the base are upgraded. Never fabricated
or estimated — a state we could not cleanly obtain is left on the floor (see STATE_BACKFILL_PROGRESS.md).

Raw sources (re-downloaded into data/work_state_returns/, gitignored due to size):
  MS  2023 gubernatorial, county   — OpenElections
        https://raw.githubusercontent.com/openelections/openelections-data-ms/master/2023/20231107__ms__general__county.csv
  LA  2023 gubernatorial open primary (Oct 14), parish — official LA SoS "Human Readable" Excel
        https://s3-us-west-2.amazonaws.com/mediaresults.sos.la.gov/HumanReadableElectionResults/20231014/Election+Results+(10-14-2023).xlsx
  NE  2022 gubernatorial, county   — official NE Board of State Canvassers canvass book (PDF)
        https://sos.nebraska.gov/sites/default/files/doc/elections/2022/2022%20General%20Canvass%20Book.pdf
  NJ  2025 gubernatorial, county   — official NJ Division of Elections statewide results (PDF)
        https://www.nj.gov/state/elections/assets/pdf/election-results/2025/2025-official-general-results-governor.pdf
  VA  2021 gubernatorial, precinct->locality — official VA Dept of Elections results CSV
        https://apps.elections.virginia.gov/SBE_CSV/ELECTIONS/ELECTIONRESULTS/2021/2021%20November%20General%20.csv
        (VA's most-recent 2025 gubernatorial is NOT cleanly machine-readable — its live ENR
         API does not expose contest/candidate results and the official CSV repo lags to 2023;
         2021 gov is the most recent clean state-level signal. See STATE_BACKFILL_PROGRESS.md.)

Requires: openpyxl, pypdf. Run from repo root: python3 scripts/build_state_returns_backfill.py
"""
import csv, json, os, re, sys, urllib.request
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "data", "work_state_returns")
OUT  = os.path.join(ROOT, "data", "processed", "state_leg_competitiveness_backfill.csv")
CANON = os.path.join(ROOT, "data", "county_scores.json")
os.makedirs(WORK, exist_ok=True)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"

def fetch(url, path):
    if os.path.exists(path):
        return path
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as r, open(path, "wb") as f:
        f.write(r.read())
    return path

def norm(s):
    return re.sub(r"\s+", "", s.lower().replace("county", "").replace("parish", "").replace(".", "").replace("'", "").replace("-", " ")).strip()

def canon_map():
    cs = json.load(open(CANON))
    m = defaultdict(dict)
    for r in cs:
        m[r["state"]][norm(r["county_name"])] = r["fips"]
    return m

def margin(D, R, tot):
    return round((D - R) / tot * 100, 3) if tot else None

# ---------------- per-state ingest -> list of (fips, D, R, total) ----------------

def ingest_ms(cmap):
    p = fetch("https://raw.githubusercontent.com/openelections/openelections-data-ms/master/2023/20231107__ms__general__county.csv",
              os.path.join(WORK, "ms_2023_general_county.csv"))
    cnt = defaultdict(lambda: defaultdict(int))
    for r in csv.DictReader(open(p)):
        if r["office"] == "Governor":
            cnt[r["county"]][r["party"]] += int(r["votes"] or 0)
    alias = {"jeffdavis": "jeffersondavis"}
    out = []
    for c, d in cnt.items():
        k = norm(c); k = alias.get(k, k)
        out.append((cmap["MS"][k], d.get("Dem", 0), d.get("Rep", 0), sum(d.values())))
    return out

def ingest_la(cmap):
    import openpyxl, warnings; warnings.filterwarnings("ignore")
    p = fetch("https://s3-us-west-2.amazonaws.com/mediaresults.sos.la.gov/HumanReadableElectionResults/20231014/Election+Results+(10-14-2023).xlsx",
              os.path.join(WORK, "la_2023_results.xlsx"))
    rows = list(openpyxl.load_workbook(p, read_only=True, data_only=True)["Multi-Parish(Parish)"].iter_rows(values_only=True))
    g = [i for i, r in enumerate(rows) if r and r[0] == "Governor"][0]
    parties = [(re.search(r"\((\w+)\)\s*$", str(c)).group(1) if c and re.search(r"\((\w+)\)\s*$", str(c)) else None) for c in rows[g + 1][1:]]
    out = []; j = g + 3
    while j < len(rows):
        r = rows[j]
        if not r or r[0] in (None, ""): break
        if r[0] == "Total Votes": j += 1; continue
        if not (len(r) > 1 and isinstance(r[1], (int, float))): break
        D = R = tot = 0
        for pty, v in zip(parties, r[1:]):
            if v is None: continue
            v = int(v); tot += v
            if pty == "DEM": D += v
            elif pty == "REP": R += v
        out.append((cmap["LA"][norm(r[0])], D, R, tot)); j += 1
    return out

def ingest_va(cmap):
    p = fetch("https://apps.elections.virginia.gov/SBE_CSV/ELECTIONS/ELECTIONRESULTS/2021/2021%20November%20General%20.csv",
              os.path.join(WORK, "va_2021_general.csv"))
    loc = defaultdict(lambda: defaultdict(int)); code = {}
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        if r["OfficeTitle"] != "Governor": continue
        code[r["LocalityName"]] = r["LocalityCode"]
        loc[r["LocalityName"]][r["Party"]] += int(r["TOTAL_VOTES"] or 0)
    out = []
    for nm, d in loc.items():
        fips = "51" + code[nm].zfill(3)
        out.append((fips, d.get("Democratic", 0), d.get("Republican", 0), sum(d.values())))
    return out

def ingest_nj(cmap):
    import pypdf
    p = fetch("https://www.nj.gov/state/elections/assets/pdf/election-results/2025/2025-official-general-results-governor.pdf",
              os.path.join(WORK, "nj_2025_gov_statewide.pdf"))
    full = "\n".join(pg.extract_text() for pg in pypdf.PdfReader(p).pages)
    COUNTIES = ["ATLANTIC","BERGEN","BURLINGTON","CAMDEN","CAPE MAY","CUMBERLAND","ESSEX","GLOUCESTER","HUDSON",
                "HUNTERDON","MERCER","MIDDLESEX","MONMOUTH","MORRIS","OCEAN","PASSAIC","SALEM","SOMERSET","SUSSEX","UNION","WARREN"]
    PARTIES = ["DEMOCRATIC","REPUBLICAN","LIBERTARIAN PARTY","SOCIALIST WORKERS PARTY"]
    cnt = defaultdict(lambda: defaultdict(int))
    for l in full.split("\n"):
        l = l.strip()
        for c in COUNTIES:
            for pty in PARTIES:
                m = re.match(r"^%s\s+%s\s+([\d,]+)$" % (re.escape(c), re.escape(pty)), l)
                if m: cnt[c][pty] += int(m.group(1).replace(",", ""))
    out = []
    for c in COUNTIES:
        d = cnt[c]
        out.append((cmap["NJ"][norm(c)], d["DEMOCRATIC"], d["REPUBLICAN"], sum(d.values())))
    return out

def ingest_ne(cmap):
    import pypdf
    p = fetch("https://sos.nebraska.gov/sites/default/files/doc/elections/2022/2022%20General%20Canvass%20Book.pdf",
              os.path.join(WORK, "ne_2022_canvass.pdf"))
    r = pypdf.PdfReader(p)
    text = "\n".join((r.pages[i].extract_text() or "") for i in (12, 13, 14))  # Governor table
    # column order in canvass book: County | Pillen(R) | Blood(D) | Zimmerman(Lib) | Write-In
    rowre = re.compile(r"^([A-Za-z][A-Za-z .]+?)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)$")
    out = []
    for l in text.split("\n"):
        m = rowre.match(l.strip())
        if not m: continue
        name = m.group(1).strip()
        if name.lower() in ("total", "county"): continue
        R, D, lib, wi = (int(m.group(i).replace(",", "")) for i in (2, 3, 4, 5))
        out.append((cmap["NE"][norm(name)], D, R, R + D + lib + wi))
    return out

SPECS = {
 "MS": (ingest_ms, "gubernatorial", 2023, "MS 2023 gubernatorial (Reeves R def. Presley D); county-level via OpenElections 20231107__ms__general__county.csv"),
 "LA": (ingest_la, "gubernatorial", 2023, "LA 2023 gubernatorial open primary (Oct 14); official LA SoS Excel Multi-Parish(Parish) sheet; margin=(sumDEM-sumREP)/total"),
 "VA": (ingest_va, "gubernatorial", 2021, "VA 2021 gubernatorial (Youngkin R def. McAuliffe D); official VA Dept of Elections precinct CSV aggregated to locality (2025 not cleanly machine-readable, see NEEDS SAM)"),
 "NJ": (ingest_nj, "gubernatorial", 2025, "NJ 2025 gubernatorial (Sherrill D def. Ciattarelli R); official NJ Div of Elections statewide results PDF county tallies"),
 "NE": (ingest_ne, "gubernatorial", 2022, "NE 2022 gubernatorial (Pillen R def. Blood D); official NE Board of State Canvassers canvass book county table"),
}

def main():
    cmap = canon_map()
    rows = []
    for st in ["VA", "NJ", "MS", "LA", "NE"]:
        fn, tier, vintage, src = SPECS[st]
        data = fn(cmap)
        for fips, D, R, tot in data:
            m = margin(D, R, tot)
            rows.append({"fips": fips, "state": st, "district_ids": "", "margin": m,
                         "competitive": abs(m) <= 3, "p1_data_tier": tier,
                         "margin_stale": False, "source": src, "vintage": vintage})
        print(f"{st}: {len(data)} counties upgraded")
    rows.sort(key=lambda r: r["fips"])
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fips","state","district_ids","margin","competitive","p1_data_tier","margin_stale","source","vintage"])
        w.writeheader()
        for r in rows:
            r["competitive"] = str(r["competitive"]); r["margin_stale"] = str(r["margin_stale"])
            w.writerow(r)
    print(f"wrote {len(rows)} rows -> {os.path.relpath(OUT, ROOT)}")

if __name__ == "__main__":
    main()
