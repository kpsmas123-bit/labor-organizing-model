"""
Ingest state-legislative competitiveness per county (state-lens P1 input).

Fallback cascade, per the most-competitive state-leg seat each county touches:
  Tier A  district_actual  - actual state-leg district D-R margin (MEDSL SLERs)
  Tier B  gubernatorial    - (NOT IMPLEMENTED: no clean national county-gov source)
  Tier C  presidential     - county presidential margin (county_scores.json margin_2024)
  none    - neither available

Sources
-------
- MEDSL "State Legislative Election Returns, 1967-2022" (doi:10.7910/DVN/FJOGJB),
  contest-level file -> most recent D-R margin per district (>=2018 cycles).
- Census 2022 State Legislative Block Equivalency Files (sldu_2022.zip / sldl_2022.zip)
  -> SLD -> county crosswalk (block membership; county = block GEOID[:5]).
- Open States current roster (data/processed/state_key_vote_scores.csv) -> stale-seat
  detection (current holder party != most-recent general-election winner party).
- county_scores.json margin_2024 -> Tier C presidential floor (canonical CT planning-region FIPS).

Aggregation rule (DOCUMENTED for scoring agent): a county's representative margin is the
MINIMUM |margin| among the NON-STALE state-leg seats that meaningfully overlap it
(block_share >= SHARE_MIN). I.e. "the most competitive seat the county touches".
A richer per-seat detail file is also emitted so the scoring agent can re-aggregate
(e.g. overlap-weighted) if desired.

Outputs
-------
  data/processed/state_leg_competitiveness.csv   (primary, per spec)
  data/work_stateleg/county_seat_detail.json     (per-county covering seats, for re-aggregation)

NOTE: read-only w.r.t. all existing canonical files. Work inputs live in data/work_stateleg/.
"""
import csv, json, zipfile, collections, os

WORK = "data/work_stateleg"
SHARE_MIN = 0.01          # drop sliver overlaps (boundary artifacts)
COMPETITIVE_PCT = 3.0     # |margin| <= 3 -> competitive
MEDSL_SINCE = 2018        # only recent cycles count toward "current"

# States whose ENTIRE most-recent MEDSL election predates their current (2022 Census BEF)
# maps: they adopted new lines and held 2023 elections (not in MEDSL through 2022), so
# MEDSL district numbers refer to OLD geography that does not align with the crosswalk.
# Tier A is unreliable for these -> demote to presidential. (NEEDS SAM: ingest 2023 results.)
DEMOTE_STATES = {"VA", "NJ", "MS"}

def unq(x): return x.strip().strip('"')

# ---------------------------------------------------------------- MEDSL Tier A
def load_medsl_latest(path):
    """Most-recent (>=2018) contest per (state_fips, chamber, dno)."""
    latest = {}
    with open(path) as fh:
        r = csv.reader(fh, delimiter="\t"); hdr = next(r)
        i = {h: n for n, h in enumerate(hdr)}
        for row in r:
            try: year = int(unq(row[i["year"]]))
            except ValueError: continue
            if year < MEDSL_SINCE: continue
            sfips = unq(row[i["sfips"]]).zfill(2)
            chamber = "U" if unq(row[i["sen"]]) == "1" else "L"
            dno = unq(row[i["dno"]])
            key = (sfips, chamber, dno)
            prev = latest.get(key)
            if prev and year <= prev["year"]: continue
            def fnum(c):
                v = unq(row[i[c]])
                return float(v) if v not in ("", ".") else 0.0
            def fwin(c):
                v = unq(row[i[c]])
                try: return float(v)
                except ValueError: return 0.0
            latest[key] = {
                "year": year, "sab": unq(row[i["sab"]]), "sfips": sfips,
                "chamber": chamber, "dno": dno,
                "dv": fnum("dvote"), "rv": fnum("rvote"), "ov": fnum("ovote"),
                "dwin": fwin("dwin"), "rwin": fwin("rwin"),
                "uncont": unq(row[i["uncont"]]),
            }
    return latest

def district_margin(v):
    """Return (margin_pct, winner_party, basis) or (None, None, None).
    margin = (D - R) / total * 100 ; positive = D lean.
    Uncontested with no recorded votes -> +/-100 via win flags (safe seat)."""
    tot = v["dv"] + v["rv"] + v["ov"]
    if tot > 0:
        m = (v["dv"] - v["rv"]) / tot * 100.0
        win = "D" if v["dv"] > v["rv"] else ("R" if v["rv"] > v["dv"] else "T")
        return round(m, 3), win, "contested" if v["uncont"] != "1" else "uncontested_votes"
    # no vote totals: use win flags (uncontested / vote-suppressed records)
    if v["dwin"] > v["rwin"]: return 100.0, "D", "uncontested_win"
    if v["rwin"] > v["dwin"]: return -100.0, "R", "uncontested_win"
    return None, None, None

# ---------------------------------------------------------------- crosswalk
def load_crosswalk(path):
    """county_fips -> list of (state_fips, chamber, code_int, block_count); + county block totals."""
    cov = collections.defaultdict(list); tot = collections.Counter()
    with open(path) as f:
        for row in csv.DictReader(f):
            cty = row["county_fips"]; bc = int(row["block_count"])
            tot[cty] += bc
            code = row["sld_code"]
            if code.isdigit():
                cov[cty].append((row["state_fips"], row["chamber"], int(code), bc))
    return cov, tot

# ---------------------------------------------------------------- Open States roster
def load_current_parties(path):
    """(state_abbr, chamber U/L, district_int) -> current party."""
    cur = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            ch = {"lower": "L", "upper": "U"}.get(row["chamber"])
            d = row["district"]
            if ch and d.isdigit():
                cur[(row["state"], ch, int(d))] = row["party"]
    return cur

# ---------------------------------------------------------------- presidential floor
def load_presidential(path):
    pres = {}
    for r in csv.DictReader(open(path)):
        m = r["margin_2024"]
        pres[r["fips"]] = (float(m) if m not in ("", "None") else None, r["state"])
    return pres

def main():
    medsl = load_medsl_latest(f"{WORK}/slers_contest_1967_2022.tab")
    # district-level margin + winner + stale
    cur = load_current_parties("data/processed/state_key_vote_scores.csv")
    dist = {}   # (sfips,chamber,code_int) -> {...}
    for (sfips, chamber, dno), v in medsl.items():
        if not dno.isdigit(): continue
        m, win, basis = district_margin(v)
        if m is None: continue
        code = int(dno)
        cp = cur.get((v["sab"], chamber, code))
        stale = bool(cp and win in ("D", "R") and cp in ("D", "R") and cp != win)
        dist[(sfips, chamber, code)] = {
            "did": f"{v['sab']}-{chamber}{code:03d}", "margin": m, "winner": win,
            "basis": basis, "year": v["year"], "current_party": cp, "stale": stale,
        }

    cov, tot = load_crosswalk(f"{WORK}/sld_county_crosswalk.csv")
    pres = load_presidential(f"{WORK}/canonical_counties.csv")

    detail = {}; out_rows = []
    tier_counts = collections.Counter()
    for fips, (pmargin, state) in pres.items():
        seats = []
        for sfips, chamber, code, bc in cov.get(fips, []):
            d = dist.get((sfips, chamber, code))
            if not d: continue
            share = bc / tot[fips] if tot[fips] else 0.0
            if share < SHARE_MIN: continue
            seats.append({**d, "share": round(share, 4)})
        detail[fips] = seats
        demoted = state in DEMOTE_STATES
        usable = [] if demoted else [s for s in seats if not s["stale"]]
        stale_dropped = [] if demoted else [s for s in seats if s["stale"]]
        if usable:
            # Prefer current-map seats (>=2022) for the competitive call; fall back to
            # old-map (2020-cycle senate) seats only when no current-map seat covers county.
            pool = [s for s in usable if s["year"] >= 2022] or usable
            rep = min(pool, key=lambda s: abs(s["margin"]))
            margin = rep["margin"]
            competitive = abs(margin) <= COMPETITIVE_PCT
            tier = "district_actual"
            # county flagged stale only if a stale seat would have changed the answer
            stale_flag = any(abs(s["margin"]) < abs(margin) for s in stale_dropped)
            vintage = rep["year"]
            did = ";".join(sorted(set(s["did"] for s in pool)))
            pre = " (pre-2022 map)" if rep["year"] < 2022 else ""
            source = "MEDSL SLERs 1967-2022 (contest-level), seat=" + rep["did"] + pre
        elif pmargin is not None:
            margin = round(pmargin, 3); competitive = abs(margin) <= COMPETITIVE_PCT
            tier = "presidential"; stale_flag = bool(stale_dropped)
            vintage = 2024; did = ""; source = "county_scores.json margin_2024 (MIT/tonmcg presidential)"
        else:
            margin = ""; competitive = ""; tier = "none"; stale_flag = bool(stale_dropped)
            vintage = ""; did = ""; source = ""
        tier_counts[tier] += 1
        out_rows.append({
            "fips": fips, "state": state, "district_ids": did, "margin": margin,
            "competitive": competitive, "p1_data_tier": tier,
            "margin_stale": stale_flag, "source": source, "vintage": vintage,
        })

    out_rows.sort(key=lambda r: r["fips"])
    with open("data/processed/state_leg_competitiveness.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fips", "state", "district_ids", "margin",
            "competitive", "p1_data_tier", "margin_stale", "source", "vintage"])
        w.writeheader(); w.writerows(out_rows)
    json.dump(detail, open(f"{WORK}/county_seat_detail.json", "w"))

    print("counties:", len(out_rows))
    print("tier counts:", dict(tier_counts))
    print("districts with margin:", len(dist),
          "| stale:", sum(1 for d in dist.values() if d["stale"]))
    print("competitive counties:", sum(1 for r in out_rows if r["competitive"] is True))

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
