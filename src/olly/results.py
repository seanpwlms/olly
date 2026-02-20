from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from olly.checks.cost import summarize_costs
from olly.models import CostRecord, DbtFinding, Finding
from olly.state import get_olly_dir


def get_default_findings_path() -> Path:
    """Return the default findings.json path for the current project."""
    return get_olly_dir() / "findings.json"


def write_findings_json(
    findings: list[Finding],
    path: Path | None = None,
    dbt_findings: list[DbtFinding] | None = None,
    cost_records: list[CostRecord] | None = None,
) -> Path:
    """Serialize findings to a JSON file.

    Args:
        findings: List of findings to write.
        path: Destination file path. Defaults to ``~/.olly/<project-hash>/findings.json``.
        dbt_findings: Optional list of dbt findings to include.

    Returns:
        The path the JSON was written to.
    """
    output_path = path or get_default_findings_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "findings": [asdict(finding) for finding in findings],
    }
    if dbt_findings:
        payload["dbt_findings"] = [asdict(f) for f in dbt_findings]
    if cost_records:
        payload["cost_summary"] = summarize_costs(cost_records)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return output_path
