from __future__ import annotations

import json
import logging
from pathlib import Path

from olly.config import DbtConfig
from olly.models import DbtFinding

logger = logging.getLogger(__name__)


def check_dbt(
    run_results_path: Path,
    settings: DbtConfig,
) -> list[DbtFinding]:
    """Check a dbt run_results.json artifact for errors and failures.

    Args:
        run_results_path: Path to the dbt ``run_results.json`` file.
        settings: dbt check configuration (thresholds, skipped handling).

    Returns:
        List of ``DbtFinding`` instances. Empty if the file is missing or
        no issues are detected.
    """
    if not run_results_path.exists():
        logger.warning("dbt run_results.json not found at %s", run_results_path)
        return []

    logger.info("Found dbt run_results.json at %s", run_results_path)

    with open(run_results_path, encoding="utf-8") as f:
        data = json.load(f)

    invocation_id = data.get("metadata", {}).get("invocation_id", "")
    results = data.get("results", [])
    logger.info("dbt run_results.json contains %d result(s)", len(results))
    findings: list[DbtFinding] = []

    for result in results:
        unique_id: str = result.get("unique_id", "")
        status: str = result.get("status", "")
        execution_time: float = result.get("execution_time", 0.0) or 0.0
        resource_type = unique_id.split(".")[0] if unique_id else "unknown"
        message: str = result.get("message", "") or ""

        compiled_code: str = (
            result.get("compiled_code") or result.get("compiled_sql") or ""
        )

        details = {
            "unique_id": unique_id,
            "resource_type": resource_type,
            "status": status,
            "execution_time": execution_time,
            "invocation_id": invocation_id,
            "compiled_code": compiled_code,
        }

        # Model/snapshot errors
        if resource_type in ("model", "snapshot") and status == "error":
            findings.append(
                DbtFinding(
                    resource_type=resource_type,
                    severity="error",
                    unique_id=unique_id,
                    status=status,
                    execution_time=execution_time,
                    description=message or f"dbt {resource_type} error",
                    details=details,
                )
            )
            continue

        # Test failures
        if resource_type == "test" and status == "fail":
            findings.append(
                DbtFinding(
                    resource_type=resource_type,
                    severity="error",
                    unique_id=unique_id,
                    status=status,
                    execution_time=execution_time,
                    description=message or "dbt test failed",
                    details=details,
                )
            )
            continue

        # Test warnings
        if resource_type == "test" and status == "warn":
            findings.append(
                DbtFinding(
                    resource_type=resource_type,
                    severity="warning",
                    unique_id=unique_id,
                    status=status,
                    execution_time=execution_time,
                    description=message or "dbt test warning",
                    details=details,
                )
            )
            continue

        # Skipped nodes
        if status == "skipped":
            if settings.include_skipped:
                findings.append(
                    DbtFinding(
                        resource_type=resource_type,
                        severity="warning",
                        unique_id=unique_id,
                        status=status,
                        execution_time=execution_time,
                        description=f"dbt node skipped: {unique_id}",
                        details=details,
                    )
                )
            continue

        # Passing nodes (success, pass, or any other unhandled status)
        findings.append(
            DbtFinding(
                resource_type=resource_type,
                severity="pass",
                unique_id=unique_id,
                status=status,
                execution_time=execution_time,
                description=message or f"dbt {resource_type} passed",
                details=details,
            )
        )

    logger.info("dbt check complete: %d finding(s) from %d result(s)", len(findings), len(results))
    return findings
