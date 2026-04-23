#!/usr/bin/env python3
"""
generate_silver.py
------------------
Generate sample audit JSON files in the silver volume folder structure.

Output layout:
  data/silver_output/YYYY-MM/UNITnnn/job_MMDDYY_HHMMSS/sales-check.json

Usage:
  cd data && uv run python generate_silver.py
"""
from __future__ import annotations

import json
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

EXIT_SUCCESS = 0

random.seed(42)

UNITS = [f"UNIT{i:03d}" for i in range(1, 11)]  # UNIT001 .. UNIT010
MONTHS_BACK = 24
OUTPUT_DIR = Path("silver_output")


def _random_ts_in_month(year: int, month: int) -> datetime:
    """Return a random datetime within the given month."""
    day = random.randint(1, 28)
    hour = random.randint(0, 23)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _generate_check(unit: str, vol_path: str, job_ts: datetime) -> dict:
    """Build a sales-check.json payload with realistic varied data."""
    total_rows = random.randint(200, 2000)
    sku_rows = random.randint(total_rows // 4, total_rows // 2)
    signed_sum = round(random.uniform(-900000, -100000), 2)
    abs_sum = round(abs(signed_sum) + random.uniform(0, 5000), 2)
    net_signed = round(random.uniform(-5000, 5000), 2)

    imbalance = round(random.uniform(0, 5000), 2)
    tolerance = 100.0
    max_var = round(random.uniform(0, 4000), 2)
    total_pairs = random.randint(50, 200)
    balanced = total_pairs - random.randint(0, 3)
    oob_passed = imbalance <= tolerance

    working_rows = random.randint(total_rows, total_rows * 2)
    load_rows = working_rows
    upload_header = sku_rows
    upload_line = working_rows
    upload_total = upload_header + upload_line
    credit_sum = abs_sum
    debit_sum = abs_sum

    ties_defs = [
        ("A→C", "Source SKU rows = Working input"),
        ("D→I", "SKU signed sum = Working upper sum"),
        ("I+J→K", "Working upper + lower = $0 balance"),
        ("L=M", "Load Credit ABS = Load Debit ABS"),
        ("L→O", "Load Credit = Upload credit adjustment sum"),
        ("M→P", "Load Debit = Upload debit adjustment sum"),
        ("O=P", "Upload Credits = Upload Debits (entry balanced)"),
        ("F≤G", "OOB net imbalance within tolerance"),
        ("rows", f"Row lineage: {sku_rows}→{working_rows}→{load_rows}→{upload_total}"),
    ]

    # Randomly fail 0-2 checks for variety
    fail_indices = set(random.sample(range(len(ties_defs)), k=random.randint(0, 2)))
    ties_result = []
    for i, (ref, desc) in enumerate(ties_defs):
        if ref == "F≤G":
            passed = oob_passed and i not in fail_indices
        else:
            passed = i not in fail_indices
        ties_result.append({"ref": ref, "description": desc, "ties": passed})

    pass_count = sum(1 for t in ties_result if t["ties"])
    fail_count = len(ties_result) - pass_count
    status = "PASS" if fail_count == 0 else ("WARN" if fail_count <= 2 else "FAIL")

    return {
        "step": "06_pipeline_lineage",
        "job_folder": vol_path,
        "timestamp": job_ts.isoformat(),
        "source": {
            "total_rows": total_rows,
            "net_signed_total": net_signed,
            "sku_PROD_7200_rows": sku_rows,
            "sku_PROD_7200_signed_sum": signed_sum,
            "sku_PROD_7200_abs_sum": abs_sum,
        },
        "oob_check": {
            "net_imbalance": imbalance,
            "tolerance": tolerance,
            "max_pair_variance": max_var,
            "total_pairs": total_pairs,
            "balanced_pairs": balanced,
            "passed": oob_passed,
        },
        "working_tab": {
            "total_rows": working_rows,
            "upper_accrued_revenue_sum": signed_sum,
            "lower_recognized_revenue_sum": round(-signed_sum, 2),
            "balance": 0.0,
        },
        "load_tab": {
            "total_rows": load_rows,
            "credit_adjustments_abs_sum": credit_sum,
            "debit_adjustments_abs_sum": debit_sum,
            "difference": 0.0,
        },
        "upload_tab": {
            "total_rows": upload_total,
            "header_rows": upload_header,
            "line_rows": upload_line,
            "credit_adjustment_sum": credit_sum,
            "debit_adjustment_sum": debit_sum,
            "entry_balance": 0.0,
        },
        "tick_and_tie": ties_result,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "overall_status": status,
    }


def main() -> int:
    """Generate the full silver folder tree with sales-check.json files."""
    now = datetime.now(timezone.utc)

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    total_files = 0
    year, month = now.year, now.month

    for _ in range(MONTHS_BACK):
        period = f"{year}-{month:02d}"

        for unit in UNITS:
            job_ts = _random_ts_in_month(year, month)
            job_name = f"job_{job_ts.strftime('%m%d%y')}_{job_ts.strftime('%H%M%S')}"

            folder = OUTPUT_DIR / period / unit / job_name
            folder.mkdir(parents=True, exist_ok=True)

            vol_path = f"/Volumes/dev/default/silver/{period}/{unit}/{job_name}"
            data = _generate_check(unit, vol_path, job_ts)

            (folder / "sales-check.json").write_text(
                json.dumps(data, indent=2), encoding="utf-8",
            )
            total_files += 1

        # Step back one month
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    print(f"Generated {total_files} sales-check.json files in {OUTPUT_DIR}/")
    print(f"  Periods: {MONTHS_BACK} months  |  Units: {len(UNITS)}")
    print("\nNext step:  make create-volume upload-data")
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
