"""
apply.py — Execute the SQL setup template against a Databricks workspace.

Reads 01_setup.sql, substitutes __CATALOG__ and __SCHEMA__ placeholders,
splits into individual statements, and executes each via the Databricks CLI.

Usage:
    python3 sql/apply.py --catalog dev --schema default --profile dev
    python3 sql/apply.py --catalog dev --schema default --dry-run
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SQL_FILE = Path(__file__).parent / "01_setup.sql"


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply SQL setup template")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument(
        "--sql-file",
        default=SQL_FILE,
        type=Path,
        help="Path to the SQL template (default: 01_setup.sql next to this script)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved statements without executing",
    )
    args = parser.parse_args()

    template = args.sql_file.read_text()
    sql = template.replace("__CATALOG__", args.catalog).replace("__SCHEMA__", args.schema)

    # Strip comment lines (-- ...) but preserve the rest of each line
    sql = re.sub(r"--[^\n]*", "", sql)

    # Split on semicolons, strip whitespace, drop empties
    statements = [s.strip() for s in sql.split(";") if s.strip()]

    total = len(statements)
    for i, stmt in enumerate(statements, 1):
        label = " ".join(stmt.split()[:6])
        print(f"[{i}/{total}] {label} …")

        if args.dry_run:
            print(f"  {stmt}\n")
            continue

        result = subprocess.run(
            [
                "databricks",
                "experimental",
                "aitools",
                "tools",
                "query",
                stmt,
                "-p",
                args.profile,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            print(f"  ❌ FAILED (exit {result.returncode})", file=sys.stderr)
            if result.stderr:
                print(f"  {result.stderr.strip()}", file=sys.stderr)
            return result.returncode
        print("  ✓")

    print(f"\n✅ All {total} statements executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
