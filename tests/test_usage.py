from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

from olly.checks.usage import check_usage
from olly.config import UsageConfig
from olly.models import UsageRecord
from helpers import FakeUsageAdapter


def _config(
    enabled: bool = True,
    lookback_days: int = 90,
    unused_threshold_days: int = 30,
    bigquery_region: str = "us",
) -> UsageConfig:
    return UsageConfig(
        enabled=enabled,
        lookback_days=lookback_days,
        unused_threshold_days=unused_threshold_days,
        bigquery_region=bigquery_region,
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
    cfg = UsageConfig(enabled=True, severity="error")
    findings = check_usage(cast(Any, adapter), ["main"], cfg)
    assert len(findings) == 2
    for f in findings:
        assert f.severity == "error"
