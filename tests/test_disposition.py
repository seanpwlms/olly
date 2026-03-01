"""Tests for the disposition feature (state store, data layer, API)."""

from __future__ import annotations

from olly.dashboard.data import (
    filter_findings,
    get_findings_stats,
    hydrate_dispositions,
)
from olly.models import Finding


# --- Data layer tests ---


def test_findings_stats_include_disposition_counts():
    findings = [
        Finding("schema", "error", "main", "orders", "d1", disposition="in_progress"),
        Finding("volume", "warning", "main", "orders", "d2", disposition="completed"),
        Finding("schema", "error", "main", "orders", "d3", disposition="not_started"),
        Finding("volume", "warning", "main", "orders", "d4", disposition="no_action"),
    ]
    stats = get_findings_stats(findings)
    assert stats.not_started_count == 1
    assert stats.in_progress_count == 1
    assert stats.no_action_count == 1
    assert stats.completed_count == 1


def test_filter_findings_by_disposition():
    findings = [
        Finding("schema", "error", "main", "orders", "Column added", disposition="in_progress"),
        Finding("volume", "warning", "main", "customers", "Z-score", disposition="completed"),
        Finding("schema", "error", "staging", "products", "Column removed"),
    ]

    in_progress = filter_findings(findings, disposition="in_progress")
    assert len(in_progress) == 1
    assert in_progress[0].table_name == "orders"

    completed = filter_findings(findings, disposition="completed")
    assert len(completed) == 1

    not_started = filter_findings(findings, disposition="not_started")
    assert len(not_started) == 1


def test_hydrate_dispositions(state_db):
    state_db.store_findings([
        Finding("schema", "error", "main", "orders", "d1"),
        Finding("volume", "warning", "main", "customers", "d2"),
    ])
    findings = state_db.get_latest_findings()
    assert all(f.disposition == "not_started" for f in findings)

    state_db.set_disposition(findings[0].id, "in_progress")
    hydrate_dispositions(findings, state_db)

    assert findings[0].disposition == "in_progress"
    assert findings[1].disposition == "not_started"


def test_hydrate_dispositions_no_findings(state_db):
    """hydrate_dispositions with empty list does nothing."""
    hydrate_dispositions([], state_db)


def test_hydrate_dispositions_no_ids(state_db):
    """Findings without ids are skipped."""
    findings = [Finding("schema", "error", "main", "orders", "d1")]
    hydrate_dispositions(findings, state_db)
    assert findings[0].disposition == "not_started"
