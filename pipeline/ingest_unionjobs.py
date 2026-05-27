"""
Wire scrape_unionjobs.py output into the normalize→classify pipeline.

Usage:
    python -m pipeline.ingest_unionjobs
        [--scraper-output output/unionjobs_raw.json]
        [--raw            data/raw_jobs.json]
        [--normalized     data/normalized_jobs.json]
        [--classified     data/classified_jobs.json]
        [--rejected       data/rejected_jobs.json]

Steps:
    1. Load scraper output (written by scripts/scrape_unionjobs.py)
    2. Construct source_url for each record: unionjobs.com/listing.php?id=...
    3. Dedupe against existing raw_jobs.json by source_url
    4. Stamp scraped_at, append new jobs, write back to raw_jobs.json
    5. Run normalize_jobs → normalized_jobs.json
    6. Run reclassify → classified_jobs.json
    7. Print summary
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


UNIONJOBS_LISTING_URL = "https://www.unionjobs.com/listing.php?id={}"


def _load_json_list(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


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


def _source_url(raw: dict):
    """Derive a stable source_url from a unionjobs scraper record."""
    if raw.get("source_url"):
        return raw["source_url"].strip()
    job_id = raw.get("job_id")
    if job_id:
        return UNIONJOBS_LISTING_URL.format(job_id)
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Merge scrape_unionjobs.py output into the normalize→classify pipeline"
    )
    parser.add_argument("--scraper-output", default="output/unionjobs_raw.json")
    parser.add_argument("--raw",            default="data/raw_jobs.json")
    parser.add_argument("--normalized",     default="data/normalized_jobs.json")
    parser.add_argument("--classified",     default="data/classified_jobs.json")
    parser.add_argument("--rejected",       default="data/rejected_jobs.json")
    args = parser.parse_args()

    if not os.path.exists(args.scraper_output):
        print(f"ERROR: scraper output not found: {args.scraper_output}")
        sys.exit(1)

    scraped = _load_json_list(args.scraper_output)
    if not scraped:
        print(f"No records in {args.scraper_output}. Nothing to do.")
        sys.exit(0)

    # Build source_url on each record and drop any that can't be identified
    for rec in scraped:
        if not rec.get("source_url"):
            rec["source_url"] = _source_url(rec)
    valid = [r for r in scraped if r.get("source_url")]
    dropped = len(scraped) - len(valid)
    if dropped:
        print(f"WARNING: dropped {dropped} records with no job_id or source_url.")

    # Dedupe against existing raw_jobs.json
    existing = _load_json_list(args.raw)
    existing_urls = {j.get("source_url", "") for j in existing}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_unique = []
    for rec in valid:
        if rec["source_url"] in existing_urls:
            continue
        if not rec.get("scraped_at"):
            rec["scraped_at"] = now
        new_unique.append(rec)

    skipped = len(valid) - len(new_unique)
    print(f"Scraped: {len(valid)} | New: {len(new_unique)} | Already in pipeline: {skipped}")

    if not new_unique:
        print("No new jobs. Nothing to write.")
        total = len(_load_json_list(args.classified))
        print(f"INGEST_NEW=0\nINGEST_SKIPPED={skipped}\nINGEST_TOTAL={total}")
        sys.exit(0)

    # Merge and write raw_jobs.json
    merged = existing + new_unique
    _write_json(args.raw, merged)
    print(f"Wrote {len(merged)} total jobs to {args.raw}.")

    # Normalize
    result = subprocess.run(
        [sys.executable, "-m", "pipeline.normalize_jobs",
         "--input",    args.raw,
         "--output",   args.normalized,
         "--rejected", args.rejected],
        capture_output=True, text=True, cwd=os.getcwd(),
    )
    _check_subprocess(result, "normalize_jobs")

    # Reclassify
    result = subprocess.run(
        [sys.executable, "-m", "pipeline.reclassify",
         "--input",  args.normalized,
         "--output", args.classified],
        capture_output=True, text=True, cwd=os.getcwd(),
    )
    _check_subprocess(result, "reclassify")

    classified = _load_json_list(args.classified)
    print()
    print("=== INGEST SUMMARY (unionjobs.com) ===")
    print(f"Scraped output: {args.scraper_output}")
    print(f"New jobs added: {len(new_unique)}")
    print(f"Duplicates skipped: {skipped}")
    print(f"Total classified: {len(classified)}")
    print()
    print(f"INGEST_NEW={len(new_unique)}")
    print(f"INGEST_SKIPPED={skipped}")
    print(f"INGEST_TOTAL={len(classified)}")


if __name__ == "__main__":
    main()
