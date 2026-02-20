from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from olly.models import Finding

if TYPE_CHECKING:
    from olly.adapter import Adapter
    from olly.config import UsageConfig

logger = logging.getLogger(__name__)


def check_usage(
    adapter: Adapter,
    schemas: list[str],
    usage_config: UsageConfig,
) -> list[Finding]:
    """Identify tables that haven't been queried in the configured period.

    Uses warehouse query history (e.g. BigQuery INFORMATION_SCHEMA.JOBS_BY_PROJECT)
    to detect tables with no recent access.

    Args:
        adapter: Warehouse adapter.
        schemas: Schema names to check usage for.
        usage_config: Usage check configuration.

    Returns:
        Findings for unused or stale tables.
    """
    try:
        usage_records = adapter.fetch_table_usage(
            schemas=schemas,
            lookback_days=usage_config.lookback_days,
            region=usage_config.bigquery_region,
        )
    except Exception:
        logger.exception("Failed to fetch table usage")
        return []

    findings: list[Finding] = []
    now = datetime.now(timezone.utc)
    threshold_days = usage_config.unused_threshold_days

    for record in usage_records:
        if record.last_queried_at is None:
            findings.append(
                Finding(
                    check_type="usage",
                    severity="error",
                    schema_name=record.schema_name,
                    table_name=record.table_name,
                    description=(
                        f"Unused table: {record.schema_name}.{record.table_name}"
                        f" — no queries in past {usage_config.lookback_days} days"
                    ),
                    details={
                        "last_queried_at": None,
                        "lookback_days": usage_config.lookback_days,
                        "threshold_days": threshold_days,
                    },
                )
            )
            continue

        last_queried = record.last_queried_at
        if last_queried.tzinfo is None:
            last_queried = last_queried.replace(tzinfo=timezone.utc)

        days_unused = (now - last_queried).total_seconds() / 86400

        if days_unused > threshold_days:
            severity = "warning" if days_unused < threshold_days * 2 else "error"
            findings.append(
                Finding(
                    check_type="usage",
                    severity=severity,
                    schema_name=record.schema_name,
                    table_name=record.table_name,
                    description=(
                        f"Stale table: {record.schema_name}.{record.table_name}"
                        f" — last queried {days_unused:.0f} days ago"
                        f" (threshold: {threshold_days} days)"
                    ),
                    details={
                        "last_queried_at": last_queried.isoformat(),
                        "days_unused": round(days_unused, 1),
                        "threshold_days": threshold_days,
                        "lookback_days": usage_config.lookback_days,
                    },
                )
            )

    return findings
