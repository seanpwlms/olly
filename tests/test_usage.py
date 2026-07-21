from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

from olly.checks.usage import (
    ROLLUP_TABLE_LIST_CAP,
    build_usage_findings,
    check_usage,
    classify_table_usage,
    summarize_schema_usage,
)
from olly.config import UsageConfig
from olly.models import UsageRecord
from helpers import FakeUsageAdapter


def _config(
    enabled: bool = True,
    lookback_days: int = 90,
    unused_threshold_days: int = 30,
    bigquery_region: str = "us",
    rollup_schemas: bool = False,
    schema_unused_threshold_pct: float = 100.0,
) -> UsageConfig:
    return UsageConfig(
        enabled=enabled,
        lookback_days=lookback_days,
        unused_threshold_days=unused_threshold_days,
        bigquery_region=bigquery_region,
        rollup_schemas=rollup_schemas,
        schema_unused_threshold_pct=schema_unused_threshold_pct,
    )


def test_unused_table_is_error():
    records = [UsageRecord("main", "dead_table", last_queried_at=None)]
    adapter = FakeUsageAdapter(records)
    findings = check_usage(cast(Any, adapter), ["main"], _config())
    assert len(findings) == 1
    assert findings[0].check_type == "usage"
    assert findings[0].severity == "warning"
    assert findings[0].table_name == "dead_table"
    assert findings[0].details["last_queried_at"] is None


def test_stale_table_warning():
    """Table beyond threshold but < 2x threshold gets warning."""
    now = datetime.now(timezone.utc)
    records = [UsageRecord("main", "stale", last_queried_at=now - timedelta(days=45))]
    adapter = FakeUsageAdapter(records)
    findings = check_usage(cast(Any, adapter), ["main"], _config())
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].details["days_unused"] > 40


def test_very_stale_table_uses_configured_severity():
    """Table beyond 2x threshold uses configured severity."""
    now = datetime.now(timezone.utc)
    records = [UsageRecord("main", "ancient", last_queried_at=now - timedelta(days=70))]
    adapter = FakeUsageAdapter(records)
    findings = check_usage(cast(Any, adapter), ["main"], _config())
    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_recently_used_no_finding():
    now = datetime.now(timezone.utc)
    records = [UsageRecord("main", "active", last_queried_at=now - timedelta(days=5))]
    adapter = FakeUsageAdapter(records)
    findings = check_usage(cast(Any, adapter), ["main"], _config())
    assert len(findings) == 0


def test_mixed_tables():
    now = datetime.now(timezone.utc)
    records = [
        UsageRecord("main", "active", now - timedelta(days=1)),
        UsageRecord("main", "stale_warn", now - timedelta(days=40)),
        UsageRecord("main", "stale_error", now - timedelta(days=80)),
        UsageRecord("main", "unused", None),
    ]
    adapter = FakeUsageAdapter(records)
    findings = check_usage(cast(Any, adapter), ["main"], _config())
    assert len(findings) == 3
    by_table = {f.table_name: f.severity for f in findings}
    assert by_table["stale_warn"] == "warning"
    assert by_table["stale_error"] == "warning"
    assert by_table["unused"] == "warning"


def test_naive_timestamp_treated_as_utc():
    """Timezone-naive timestamps should be handled without error."""
    now = datetime.now(timezone.utc)
    naive = (now - timedelta(days=45)).replace(tzinfo=None)
    records = [UsageRecord("main", "naive_ts", last_queried_at=naive)]
    adapter = FakeUsageAdapter(records)
    findings = check_usage(cast(Any, adapter), ["main"], _config())
    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_empty_records():
    adapter = FakeUsageAdapter([])
    findings = check_usage(cast(Any, adapter), ["main"], _config())
    assert len(findings) == 0


def test_all_tables_flags_missing_from_query_history():
    """Tables in all_tables but absent from usage records are flagged as unused."""
    now = datetime.now(timezone.utc)
    records = [UsageRecord("main", "active", now - timedelta(days=1))]
    adapter = FakeUsageAdapter(records)
    all_tables = [("main", "active"), ("main", "orphan"), ("other", "ghost")]
    findings = check_usage(cast(Any, adapter), ["main"], _config(), all_tables=all_tables)
    assert len(findings) == 2
    missing = {(f.schema_name, f.table_name) for f in findings}
    assert ("main", "orphan") in missing
    assert ("other", "ghost") in missing
    for f in findings:
        assert f.severity == "warning"
        assert f.details["last_queried_at"] is None


def test_usage_check_skipped_on_unsupported_adapter():
    """Adapters without SUPPORTS_USAGE_HISTORY return no findings even with all_tables."""
    class UnsupportedAdapter:
        SUPPORTS_USAGE_HISTORY = False

        def fetch_table_usage(self, schemas, lookback_days, region="us"):
            return []

    findings = check_usage(
        cast(Any, UnsupportedAdapter()),
        ["main"],
        _config(),
        all_tables=[("main", "t1"), ("main", "t2")],
    )
    assert findings == []


def test_severity_config_override():
    """Setting severity='error' in config propagates to all findings."""
    now = datetime.now(timezone.utc)
    records = [
        UsageRecord("main", "stale", now - timedelta(days=45)),
        UsageRecord("main", "unused", None),
    ]
    adapter = FakeUsageAdapter(records)
    cfg = UsageConfig(enabled=True, severity="error", rollup_schemas=False)
    findings = check_usage(cast(Any, adapter), ["main"], cfg)
    assert len(findings) == 2
    for f in findings:
        assert f.severity == "error"


def test_rollup_fully_inactive_schema():
    """A schema with no active tables collapses into one schema finding."""
    now = datetime.now(timezone.utc)
    records = [
        UsageRecord("dead", "t1", None),
        UsageRecord("dead", "t2", now - timedelta(days=60)),
    ]
    adapter = FakeUsageAdapter(records)
    findings = check_usage(
        cast(Any, adapter), ["dead"], _config(rollup_schemas=True)
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.check_type == "usage"
    assert f.schema_name == "dead"
    assert f.table_name == "*"
    assert "Unused schema: dead" in f.description
    assert f.details["scope"] == "schema"
    assert f.details["table_count"] == 2
    assert f.details["unused_count"] == 1
    assert f.details["stale_count"] == 1
    assert f.details["inactive_pct"] == 100.0
    assert f.details["tables"] == ["t1", "t2"]
    assert f.details["tables_truncated"] is False
    assert f.details["last_activity_at"] is not None


def test_rollup_skips_schema_with_active_table():
    """Default 100% threshold: an active table prevents the rollup."""
    now = datetime.now(timezone.utc)
    records = [
        UsageRecord("main", "active", now - timedelta(days=1)),
        UsageRecord("main", "unused", None),
    ]
    adapter = FakeUsageAdapter(records)
    findings = check_usage(
        cast(Any, adapter), ["main"], _config(rollup_schemas=True)
    )
    assert len(findings) == 1
    assert findings[0].table_name == "unused"


def test_rollup_partial_threshold_keeps_table_findings():
    """Below-100% threshold emits a schema finding alongside table findings."""
    now = datetime.now(timezone.utc)
    records = [
        UsageRecord("main", "active", now - timedelta(days=1)),
        UsageRecord("main", "unused_a", None),
        UsageRecord("main", "unused_b", None),
    ]
    adapter = FakeUsageAdapter(records)
    findings = check_usage(
        cast(Any, adapter),
        ["main"],
        _config(rollup_schemas=True, schema_unused_threshold_pct=50.0),
    )
    by_table = {f.table_name for f in findings}
    assert by_table == {"*", "unused_a", "unused_b"}
    schema_finding = next(f for f in findings if f.table_name == "*")
    assert "Mostly unused schema: main" in schema_finding.description
    assert schema_finding.details["inactive_pct"] == 66.7
    assert schema_finding.details["last_activity_at"] is not None


def test_rollup_multiple_schemas():
    """Only fully-inactive schemas roll up; healthy schemas keep table findings."""
    now = datetime.now(timezone.utc)
    records = [
        UsageRecord("dead", "t1", None),
        UsageRecord("dead", "t2", None),
        UsageRecord("live", "active", now - timedelta(days=1)),
        UsageRecord("live", "unused", None),
    ]
    adapter = FakeUsageAdapter(records)
    findings = check_usage(
        cast(Any, adapter), ["dead", "live"], _config(rollup_schemas=True)
    )
    assert len(findings) == 2
    by_schema = {(f.schema_name, f.table_name) for f in findings}
    assert by_schema == {("dead", "*"), ("live", "unused")}


def test_rollup_table_list_capped():
    """Schema finding embeds at most ROLLUP_TABLE_LIST_CAP table names."""
    n = ROLLUP_TABLE_LIST_CAP + 5
    records = [UsageRecord("dead", f"t{i:03d}", None) for i in range(n)]
    adapter = FakeUsageAdapter(records)
    findings = check_usage(
        cast(Any, adapter), ["dead"], _config(rollup_schemas=True)
    )
    assert len(findings) == 1
    details = findings[0].details
    assert details["table_count"] == n
    assert len(details["tables"]) == ROLLUP_TABLE_LIST_CAP
    assert details["tables_truncated"] is True


def test_classify_table_usage():
    """Tables are classified active/stale/unused, sorted by schema and table."""
    now = datetime.now(timezone.utc)
    records = [
        UsageRecord("main", "stale", now - timedelta(days=45)),
        UsageRecord("main", "active", now - timedelta(days=2)),
    ]
    adapter = FakeUsageAdapter(records)
    statuses = classify_table_usage(
        cast(Any, adapter),
        ["main"],
        _config(),
        all_tables=[("main", "orphan")],
    )
    assert [(s.table_name, s.status) for s in statuses] == [
        ("active", "active"),
        ("orphan", "unused"),
        ("stale", "stale"),
    ]
    assert statuses[1].last_queried_at is None
    assert statuses[2].days_unused is not None and statuses[2].days_unused > 40


def test_summarize_schema_usage():
    """Summaries aggregate counts per schema, most inactive first."""
    now = datetime.now(timezone.utc)
    records = [
        UsageRecord("dead", "t1", None),
        UsageRecord("mixed", "active", now - timedelta(days=1)),
        UsageRecord("mixed", "stale", now - timedelta(days=50)),
    ]
    adapter = FakeUsageAdapter(records)
    statuses = classify_table_usage(cast(Any, adapter), ["dead", "mixed"], _config())
    summaries = summarize_schema_usage(statuses)
    assert [s.schema_name for s in summaries] == ["dead", "mixed"]

    dead, mixed = summaries
    assert dead.total_tables == 1
    assert dead.unused_count == 1
    assert dead.inactive_pct == 100.0
    assert dead.fully_inactive is True
    assert dead.last_activity_at is None

    assert mixed.total_tables == 2
    assert mixed.active_count == 1
    assert mixed.stale_count == 1
    assert mixed.inactive_pct == 50.0
    assert mixed.fully_inactive is False
    assert mixed.last_activity_at is not None


def test_build_usage_findings_empty_statuses():
    """No statuses produce no findings, with or without rollup."""
    assert build_usage_findings([], _config(rollup_schemas=True)) == []
