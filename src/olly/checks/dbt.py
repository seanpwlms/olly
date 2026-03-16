from __future__ import annotations

import json
import logging
from pathlib import Path

from olly.config import DbtConfig
from olly.models import DbtFinding, DbtRunRecord

logger = logging.getLogger(__name__)


def check_dbt(
    run_results_path: Path,
    settings: DbtConfig,
) -> tuple[list[DbtFinding], DbtRunRecord | None]:
    """Check a dbt run_results.json artifact for errors and failures.

    Args:
        run_results_path: Path to the dbt ``run_results.json`` file.
        settings: dbt check configuration (thresholds, skipped handling).

    Returns:
        Tuple of (list of findings, run record or None if file missing).
    """
    if not run_results_path.exists():
        logger.warning("dbt run_results.json not found at %s", run_results_path)
        return [], None

    logger.info("Found dbt run_results.json at %s", run_results_path)

    with open(run_results_path, encoding="utf-8") as f:
        data = json.load(f)

    invocation_id = data.get("metadata", {}).get("invocation_id", "")
    elapsed_time = data.get("elapsed_time", 0.0) or 0.0
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

        failures = result.get("failures")
        adapter_response: dict = result.get("adapter_response", {}) or {}

        details = {
            "unique_id": unique_id,
            "resource_type": resource_type,
            "status": status,
            "execution_time": execution_time,
            "invocation_id": invocation_id,
            "compiled_code": compiled_code,
            "failures": failures,
            "adapter_response": adapter_response,
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
                        description=message or f"dbt node skipped: {unique_id}",
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

    # Detect cascade groups: skipped nodes whose message references an errored model
    _detect_cascades(findings)

    # Build run record
    error_count = sum(1 for f in findings if f.severity == "error")
    warning_count = sum(1 for f in findings if f.severity == "warning")
    pass_count = sum(1 for f in findings if f.severity == "pass")
    run_record = DbtRunRecord(
        invocation_id=invocation_id,
        elapsed_time=elapsed_time,
        total_nodes=len(results),
        error_count=error_count,
        warning_count=warning_count,
        pass_count=pass_count,
    )

    logger.info("dbt check complete: %d finding(s) from %d result(s)", len(findings), len(results))
    return findings, run_record


def _detect_cascades(findings: list[DbtFinding]) -> None:
    """Annotate findings with cascade group info in-place.

    Looks for skipped/error findings whose message references an errored model.
    Adds ``cascade_root`` to downstream findings' details.
    """
    # Collect errored model names (short name, e.g. "orders" from "model.project.orders")
    error_nodes: dict[str, str] = {}
    for f in findings:
        if f.severity == "error" and f.resource_type in ("model", "snapshot"):
            parts = f.unique_id.split(".")
            short_name = parts[-1] if parts else f.unique_id
            error_nodes[short_name] = f.unique_id

    if not error_nodes:
        return

    for f in findings:
        if f.unique_id in error_nodes.values():
            continue
        desc_lower = f.description.lower()
        for short_name, full_id in error_nodes.items():
            if short_name.lower() in desc_lower:
                f.details["cascade_root"] = full_id
                break
