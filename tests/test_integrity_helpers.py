from datetime import datetime, timedelta

import pytest

from olly.checks.integrity import (
    _build_where_sql,
    _compare_numeric,
    _parse_table_ref,
    _parse_timestamp,
    _resolve_window,
)
from olly.models import IntegrityMethod, Sync, WindowOp, WindowSpec


# --- Window operation tests ---


def test_resolve_window_gt_now():
    pipeline = Sync(
        name="p",
        source="s",
        target="t",
        source_table="a.b",
        target_table="a.b",
        method=IntegrityMethod.COUNT,
        window=WindowSpec(op=WindowOp.GT_NOW, duration="2h"),
    )
    start, end = _resolve_window(pipeline)
    assert end > start
    assert (end - start) - timedelta(hours=2) < timedelta(seconds=2)


def test_resolve_window_eq_ts():
    pipeline = Sync(
        name="p",
        source="s",
        target="t",
        source_table="a.b",
        target_table="a.b",
        method=IntegrityMethod.COUNT,
        window=WindowSpec(op=WindowOp.EQ_TS, value="2026-02-16 12:00:00"),
    )
    start, end = _resolve_window(pipeline)
    assert start == end == datetime(2026, 2, 16, 12, 0, 0)


def test_resolve_window_eq_date():
    pipeline = Sync(
        name="p",
        source="s",
        target="t",
        source_table="a.b",
        target_table="a.b",
        method=IntegrityMethod.COUNT,
        window=WindowSpec(op=WindowOp.EQ_DATE, value="2026-02-16"),
    )
    start, end = _resolve_window(pipeline)
    assert start == datetime(2026, 2, 16, 0, 0, 0)
    assert end == datetime(2026, 2, 16, 23, 59, 59, 999999)


def test_resolve_window_gt_now_missing_duration():
    pipeline = Sync(
        name="p",
        source="s",
        target="t",
        source_table="a.b",
        target_table="a.b",
        method=IntegrityMethod.COUNT,
        window=WindowSpec(op=WindowOp.GT_NOW),
    )
    with pytest.raises(ValueError, match="duration"):
        _resolve_window(pipeline)


def test_resolve_window_between_missing_start_end():
    pipeline = Sync(
        name="p",
        source="s",
        target="t",
        source_table="a.b",
        target_table="a.b",
        method=IntegrityMethod.COUNT,
        window=WindowSpec(op=WindowOp.BETWEEN),
    )
    with pytest.raises(ValueError, match="start/end"):
        _resolve_window(pipeline)


# --- Tolerance logic tests ---


def test_compare_numeric_tolerance_delta_passes():
    pipeline = Sync(
        name="p",
        source="s",
        target="t",
        source_table="a.b",
        target_table="a.b",
        method=IntegrityMethod.COUNT,
        tolerance_delta=5,
    )
    now = datetime.now()
    result = _compare_numeric(pipeline, "s", "t", 100, 97, now, now)
    assert result is None


def test_compare_numeric_tolerance_delta_and_ratio():
    """Either tolerance_delta OR tolerance_ratio passing -> passes."""
    pipeline = Sync(
        name="p",
        source="s",
        target="t",
        source_table="a.b",
        target_table="a.b",
        method=IntegrityMethod.COUNT,
        tolerance_delta=1,
        tolerance_ratio=0.9,
    )
    now = datetime.now()
    # diff=5 exceeds delta=1, but ratio=95/100=0.95 >= 0.9 -> passes
    result = _compare_numeric(pipeline, "s", "t", 100, 95, now, now)
    assert result is None


def test_compare_numeric_zero_zero_passes():
    pipeline = Sync(
        name="p",
        source="s",
        target="t",
        source_table="a.b",
        target_table="a.b",
        method=IntegrityMethod.COUNT,
        tolerance_ratio=0.9,
    )
    now = datetime.now()
    result = _compare_numeric(pipeline, "s", "t", 0, 0, now, now)
    assert result is None


# --- Helper tests ---


def test_parse_table_ref_no_dot():
    with pytest.raises(ValueError, match="schema.table"):
        _parse_table_ref("orders")


def test_build_where_sql_with_extra_clause():
    result = _build_where_sql(
        "updated_at",
        datetime(2026, 1, 1),
        datetime(2026, 1, 2),
        "status = 'active'",
    )
    assert "status = 'active'" in result
    assert "updated_at >=" in result


def test_parse_timestamp_z_suffix():
    result = _parse_timestamp("2026-02-16T12:00:00Z")
    assert result == datetime(2026, 2, 16, 12, 0, 0)
    assert result.tzinfo is None


def test_parse_timestamp_with_timezone():
    result = _parse_timestamp("2026-02-16T12:00:00+05:00")
    assert result == datetime(2026, 2, 16, 12, 0, 0)
    assert result.tzinfo is None
