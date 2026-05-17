"""
URL ingestion orchestrator.

Usage:
    python -m pipeline.ingest_url --url <URL> [--mode auto|single|board]
                                  [--raw data/raw_jobs.json]
                                  [--normalized data/normalized_jobs.json]
                                  [--classified data/classified_jobs.json]
                                  [--rejected data/rejected_jobs.json]

Steps:
    1. Ingest via router (detect board, check robots.txt, scrape)
    2. Dedupe against existing data/raw_jobs.json by source_url
    3. Append new jobs and write back
    4. Run normalize_jobs → normalized_jobs.json
    5. Run reclassify → classified_jobs.json
    6. Print machine-parseable summary + confidence breakdown
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def _load_json_list(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return []


def _write_json(path, data):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _check_subprocess(result, name):
    combined = (result.stdout or "") + (result.stderr or "")
    if combined.strip():
        print(f"[{name}] {combined.strip()}")
    if result.returncode != 0:
        print(f"ERROR: {name} exited with code {result.returncode}")
        sys.exit(result.returncode)


def _confidence_breakdown(jobs):
    """Returns dict: tier label → count."""
    tiers = {"1.0 (JSON-LD)": 0, "0.7-0.9 (structured)": 0, "0.4-0.6 (partial)": 0, "<0.4 (heuristic)": 0}
    for job in jobs:
        c = job.get("confidence", 0.5)
        if c >= 1.0:
            tiers["1.0 (JSON-LD)"] += 1
        elif c >= 0.7:
            tiers["0.7-0.9 (structured)"] += 1
        elif c >= 0.4:
            tiers["0.4-0.6 (partial)"] += 1
        else:
            tiers["<0.4 (heuristic)"] += 1
    return tiers


def main():
    parser = argparse.ArgumentParser(description="Ingest jobs from a URL into the pipeline")
    parser.add_argument("--url", required=True, help="Job board or single job URL to ingest")
    parser.add_argument("--mode", default="auto", choices=["auto", "single", "board"],
                        help="Ingestion mode (default: auto)")
    parser.add_argument("--raw",        default="data/raw_jobs.json")
    parser.add_argument("--normalized", default="data/normalized_jobs.json")
    parser.add_argument("--classified", default="data/classified_jobs.json")
    parser.add_argument("--rejected",   default="data/rejected_jobs.json")
    args = parser.parse_args()

    url = args.url.strip()

    # 1. Run ingestor
    from pipeline.ingestors.router import ingest, RobotsDisallowedError
    try:
        new_jobs = ingest(url, mode=args.mode)
    except RobotsDisallowedError as e:
        print(f"ABORTED: robots.txt disallows scraping {url}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Ingestor failed for {url}: {e}")
        sys.exit(1)

    if not new_jobs:
        print(f"No jobs extracted from {url}")
        print("INGEST_NEW=0")
        print("INGEST_SKIPPED=0")
        total = len(_load_json_list(args.classified))
        print(f"INGEST_TOTAL={total}")
        sys.exit(0)

    # 2. Load existing raw_jobs.json
    existing = _load_json_list(args.raw)
    existing_urls = {j.get("source_url", "") for j in existing}

    # 3. Dedupe
    new_unique = [j for j in new_jobs if j.get("source_url") and j["source_url"] not in existing_urls]
    skipped = len(new_jobs) - len(new_unique)

    # Stamp scraped_at on anything that's missing it
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for job in new_unique:
        if not job.get("scraped_at"):
            job["scraped_at"] = now

    if not new_unique:
        print(f"All {len(new_jobs)} jobs already in raw_jobs.json (0 new).")
        print("INGEST_NEW=0")
        print(f"INGEST_SKIPPED={skipped}")
        total = len(_load_json_list(args.classified))
        print(f"INGEST_TOTAL={total}")
        sys.exit(0)

    # 4. Write merged raw_jobs.json
    merged = existing + new_unique
    _write_json(args.raw, merged)
    print(f"Wrote {len(merged)} total jobs to {args.raw} ({len(new_unique)} new, {skipped} skipped).")

    # 5. Normalize
    result = subprocess.run(
        [sys.executable, "-m", "pipeline.normalize_jobs",
         "--input", args.raw,
         "--output", args.normalized,
         "--rejected", args.rejected],
        capture_output=True, text=True, cwd=os.getcwd(),
    )
    _check_subprocess(result, "normalize_jobs")

    # 6. Reclassify
    result = subprocess.run(
        [sys.executable, "-m", "pipeline.reclassify",
         "--input", args.normalized,
         "--output", args.classified],
        capture_output=True, text=True, cwd=os.getcwd(),
    )
    _check_subprocess(result, "reclassify")

    # 7. Summary
    classified = _load_json_list(args.classified)

    print()
    print("=== INGESTION SUMMARY ===")
    print(f"URL:         {url}")
    print(f"Mode:        {args.mode}")
    print(f"Extracted:   {len(new_jobs)} raw jobs")
    print(f"New (unique):{len(new_unique)} added to raw_jobs.json")
    print(f"Skipped:     {skipped} duplicates")
    print(f"Total classified: {len(classified)}")
    tiers = _confidence_breakdown(new_unique)
    print("Confidence breakdown:")
    for tier, count in tiers.items():
        if count:
            print(f"  {tier}: {count}")
    print()

    # Machine-parseable lines (read by admin_server.py)
    print(f"INGEST_NEW={len(new_unique)}")
    print(f"INGEST_SKIPPED={skipped}")
    print(f"INGEST_TOTAL={len(classified)}")


if __name__ == "__main__":
    main()
