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

# --- VA source: SINGLE SWAP POINT --------------------------------------------
# VA is on 2021 gubernatorial because the most-recent 2025 race is not yet cleanly
# machine-readable (the live ENR API exposes no contest/candidate results, and VA's
# official bulk-CSV repo lags — latest folder is 2023). check_va_2025_availability()
# probes the 2025 file every build and logs whether it has appeared yet.
#
# TO UPGRADE TO 2025 once the file exists, change exactly THREE things:
#   1. VA_ACTIVE_URL  -> VA_2025_URL   (below)
#   2. SPECS["VA"]     vintage 2021 -> 2025  (and update the source string)
#   3. EXPECTED_STATEWIDE["VA"] -> the 2025 certified D-R margin (~ +14.9)
# Nothing else changes: precinct->locality aggregation and VA FIPS are year-agnostic.
VA_2021_URL = "https://apps.elections.virginia.gov/SBE_CSV/ELECTIONS/ELECTIONRESULTS/2021/2021%20November%20General%20.csv"
VA_2025_URL = "https://apps.elections.virginia.gov/SBE_CSV/ELECTIONS/ELECTIONRESULTS/2025/2025%20November%20General%20.csv"
VA_ACTIVE_URL = VA_2021_URL  # <-- swap to VA_2025_URL when available (see note above)

def ingest_va(cmap):
    p = fetch(VA_ACTIVE_URL, os.path.join(WORK, "va_general.csv"))
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

# ---------------------------- validation ------------------------------------
# Expected per-state county counts (canonical FIPS universe for each state).
EXPECTED_COUNTS = {"VA": 133, "NJ": 21, "MS": 82, "LA": 64, "NE": 93}
# Vote-weighted statewide D-R margin (%), each verified against the published
# certified statewide result at build time. A re-run must reconcile to within
# STATEWIDE_TOL points of these, else the build FAILS (won't ship a bad CSV).
#   VA 2021: Youngkin R+1.9   NJ 2025: Sherrill D+14.4   MS 2023: Reeves R+3.x
#   LA 2023: Landry-led R blowout (jungle, party-summed)  NE 2022: Pillen R+23
EXPECTED_STATEWIDE = {"VA": -1.94, "NJ": 14.36, "MS": -3.42, "LA": -36.98, "NE": -23.24}
STATEWIDE_TOL = 2.0          # points; statewide reconciliation tolerance (hard fail)
OUTLIER_THRESHOLD = 45.0     # points; county deviation from state mean -> warn (soft)
LA_MIN_SPREAD = 20.0         # points; LA jungle-primary distribution must not be degenerate

def check_va_2025_availability():
    """Probe the VA bulk-CSV repo for a 2025 General file; log availability (never fails)."""
    import urllib.error
    if VA_ACTIVE_URL == VA_2025_URL:
        print("[VA-2025 check] already running on the 2025 file."); return
    try:
        req = urllib.request.Request(VA_2025_URL, headers={"User-Agent": UA}, method="HEAD")
        with urllib.request.urlopen(req, timeout=20) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:
        print(f"[VA-2025 check] could not reach VA repo ({e}); staying on 2021."); return
    if code == 200:
        print("[VA-2025 check] *** 2025 General CSV IS NOW AVAILABLE *** -> "
              f"{VA_2025_URL}\n               Swap VA_ACTIVE_URL=VA_2025_URL, bump SPECS['VA'] "
              "vintage->2025, and set EXPECTED_STATEWIDE['VA'] to the 2025 certified margin (~+14.9).")
    else:
        print(f"[VA-2025 check] 2025 General CSV not available yet (HTTP {code}); staying on 2021 gubernatorial.")

def validate(details, cmap):
    """Sanity-check the rebuilt data. Raises SystemExit(1) on any hard failure BEFORE the
    CSV is written, so a bad re-run cannot silently ship. details: {st:[(fips,D,R,tot,margin)]}."""
    import statistics
    canon_fips = {f for st in cmap for f in cmap[st].values()}
    failures = []
    print("\n=== VALIDATION ===")
    for st, recs in details.items():
        # (a) county count
        if len(recs) != EXPECTED_COUNTS[st]:
            failures.append(f"{st}: county count {len(recs)} != expected {EXPECTED_COUNTS[st]}")
        # (b) every margin finite & in [-100,100]; every fips canonical
        for fips, D, R, tot, m in recs:
            if m is None or m != m:                      # None or NaN
                failures.append(f"{st} {fips}: margin is null/NaN")
            elif not (-100.0 <= m <= 100.0):
                failures.append(f"{st} {fips}: margin {m} outside [-100,+100]")
            if fips not in canon_fips:
                failures.append(f"{st} {fips}: not a canonical FIPS")
        # (c) vote-weighted statewide reconciliation
        D = sum(r[1] for r in recs); R = sum(r[2] for r in recs); T = sum(r[3] for r in recs)
        agg = (D - R) / T * 100 if T else float("nan")
        exp = EXPECTED_STATEWIDE[st]
        if not (abs(agg - exp) <= STATEWIDE_TOL):
            failures.append(f"{st}: statewide {agg:+.2f}% not within +/-{STATEWIDE_TOL} of expected {exp:+.2f}%")
        else:
            print(f"  {st}: {len(recs)} counties · statewide {agg:+.2f}% (exp {exp:+.2f}%, within +/-{STATEWIDE_TOL}) OK")
    # (d) LA-specific: jungle-primary margin is coarse — assert distribution isn't degenerate
    la = [r[4] for r in details["LA"]]
    if len({1 if x > 0 else -1 for x in la}) < 2:
        failures.append("LA: all parish margins share one sign (degenerate distribution)")
    la_spread = max(la) - min(la)
    if la_spread < LA_MIN_SPREAD:
        failures.append(f"LA: margin spread {la_spread:.1f} < {LA_MIN_SPREAD} (degenerate)")
    print(f"  LA distribution (jungle-primary, eyeball): min={min(la):+.1f} "
          f"median={statistics.median(la):+.1f} max={max(la):+.1f} spread={la_spread:.1f}")
    # (e) outlier flag (warn only): county margin far from its state mean -> manual review
    for st, recs in details.items():
        mean = statistics.fmean(r[4] for r in recs)
        for fips, D, R, tot, m in recs:
            if abs(m - mean) > OUTLIER_THRESHOLD:
                print(f"  [outlier:review] {st} {fips}: margin {m:+.1f} deviates {m-mean:+.1f}pp "
                      f"from {st} mean {mean:+.1f} (n={tot} votes)")
    # summary
    if failures:
        print("\nVALIDATION: FAIL  (CSV not written)")
        for f in failures:
            print("  X", f)
        raise SystemExit(1)
    print("\nVALIDATION: PASS  — all hard checks green\n")

def main():
    cmap = canon_map()
    check_va_2025_availability()
    details = {}
    for st in ["VA", "NJ", "MS", "LA", "NE"]:
        fn, tier, vintage, src = SPECS[st]
        data = fn(cmap)                                   # [(fips, D, R, tot), ...]
        details[st] = [(fips, D, R, tot, margin(D, R, tot)) for fips, D, R, tot in data]
        print(f"{st}: {len(data)} counties upgraded")
    validate(details, cmap)                               # raises on failure BEFORE writing
    rows = []
    for st in ["VA", "NJ", "MS", "LA", "NE"]:
        _, tier, vintage, src = SPECS[st]
        for fips, D, R, tot, m in details[st]:
            rows.append({"fips": fips, "state": st, "district_ids": "", "margin": m,
                         "competitive": abs(m) <= 3, "p1_data_tier": tier,
                         "margin_stale": False, "source": src, "vintage": vintage})
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
