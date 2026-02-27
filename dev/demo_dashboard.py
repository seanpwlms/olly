"""Seed data and launch the Olly dashboard for a demo.

Usage:
    uv run python dev/demo_dashboard.py          # seed + start server
    uv run python dev/demo_dashboard.py --no-serve  # seed only, skip server
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from seed_dashboard_data import seed_rich_dashboard_data
from seed_db import (
    DEV_DIR,
    drift,
    run_checks_in_dev,
    setup,
)

from olly.results import write_findings_json


def main() -> None:
    no_serve = "--no-serve" in sys.argv

    # 1. Fresh setup: DB, config, integrity DBs, dbt results, 2 baseline snapshots
    config = setup()

    # 2. Generate rich historical data (30 days of snapshots, findings, cost data)
    seed_rich_dashboard_data(config)

    # 3. Introduce drift (schema, volume, freshness, contracts, integrity)
    drift(config)

    # 4. Run live checks so dashboard shows current findings
    os.chdir(DEV_DIR)
    findings, dbt_findings = run_checks_in_dev(config)
    findings_path = write_findings_json(findings, dbt_findings=dbt_findings)
    print(f"\nWrote {len(findings)} findings to {findings_path}")

    for f in findings:
        print(
            f"  [{f.severity}] {f.check_type}: {f.schema_name}.{f.table_name} — {f.description}"
        )

    if no_serve:
        print("\nDone. Run 'cd dev && uv run olly serve' to start the dashboard.")
        return

    # 5. Start the dashboard
    print("\nStarting dashboard at http://127.0.0.1:8000 ...")
    from olly.cli.serve import run_serve

    run_serve()


if __name__ == "__main__":
    main()
