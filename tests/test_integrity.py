from datetime import timedelta

import duckdb
import pytest

from olly.checks.integrity import _parse_duration, run_syncs
from olly.models import IntegrityMethod, Sync, WindowOp, WindowSpec


@pytest.mark.parametrize(
    "value, expected",
    [
        ("30s", timedelta(seconds=30)),
        ("5m", timedelta(minutes=5)),
        ("2h", timedelta(hours=2)),
        ("7d", timedelta(days=7)),
    ],
)
def test_parse_duration(value, expected):
    assert _parse_duration(value) == expected


def test_parse_duration_invalid():
    with pytest.raises(ValueError, match="Invalid duration"):
        _parse_duration("abc")


def _create_orders_db(path, rows):
    conn = duckdb.connect(str(path))
    conn.execute(
        "CREATE TABLE orders ("
        "  id INTEGER NOT NULL,"
        "  customer_id INTEGER NOT NULL,"
        "  amount DOUBLE NOT NULL,"
        "  updated_at TIMESTAMP NOT NULL"
        ")"
    )
    for row in rows:
        conn.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?)",
            row,
        )
    conn.close()


def test_integrity_count_match(tmp_path):
    source_path = tmp_path / "source.duckdb"
    rows = [
        (1, 1, 99.99, "2026-02-16 10:00:00"),
        (2, 2, 49.50, "2026-02-16 11:00:00"),
        (3, 1, 25.00, "2026-02-15 09:00:00"),
    ]
    _create_orders_db(source_path, rows)

    sources = {
        "source": f"duckdb:///{source_path}",
        "target": f"duckdb:///{source_path}",
    }

    pipelines = [
        Sync(
            name="orders_sync",
            source="source",
            target="target",
            source_table="main.orders",
            target_table="main.orders",
            method=IntegrityMethod.COUNT,
            watermark="updated_at",
            window=WindowSpec(
                op=WindowOp.BETWEEN,
                start="2026-02-15 00:00:00",
                end="2026-02-16 23:59:59",
            ),
        )
    ]

    findings = run_syncs(pipelines, sources=sources)
    assert findings == []


def test_integrity_count_mismatch(tmp_path):
    source_path = tmp_path / "source.duckdb"
    target_path = tmp_path / "target.duckdb"
    source_rows = [
        (1, 1, 99.99, "2026-02-16 10:00:00"),
        (2, 2, 49.50, "2026-02-16 11:00:00"),
        (3, 1, 25.00, "2026-02-15 09:00:00"),
    ]
    target_rows = [
        (1, 1, 99.99, "2026-02-16 10:00:00"),
        (2, 2, 49.50, "2026-02-16 11:00:00"),
    ]
    _create_orders_db(source_path, source_rows)
    _create_orders_db(target_path, target_rows)

    sources = {
        "source": f"duckdb:///{source_path}",
        "target": f"duckdb:///{target_path}",
    }

    pipelines = [
        Sync(
            name="orders_sync",
            source="source",
            target="target",
            source_table="main.orders",
            target_table="main.orders",
            method=IntegrityMethod.COUNT,
            watermark="updated_at",
            window=WindowSpec(
                op=WindowOp.BETWEEN,
                start="2026-02-15 00:00:00",
                end="2026-02-16 23:59:59",
            ),
        )
    ]

    findings = run_syncs(pipelines, sources=sources)
    assert len(findings) == 1
    assert findings[0].check_type == "integrity"


def test_integrity_count_distinct(tmp_path):
    source_path = tmp_path / "source.duckdb"
    target_path = tmp_path / "target.duckdb"
    source_rows = [
        (1, 1, 99.99, "2026-02-16 10:00:00"),
        (2, 2, 49.50, "2026-02-16 11:00:00"),
        (3, 3, 25.00, "2026-02-15 09:00:00"),
    ]
    target_rows = [
        (1, 1, 99.99, "2026-02-16 10:00:00"),
        (2, 2, 49.50, "2026-02-16 11:00:00"),
    ]
    _create_orders_db(source_path, source_rows)
    _create_orders_db(target_path, target_rows)

    sources = {
        "source": f"duckdb:///{source_path}",
        "target": f"duckdb:///{target_path}",
    }

    pipelines = [
        Sync(
            name="orders_distinct",
            source="source",
            target="target",
            source_table="main.orders",
            target_table="main.orders",
            method=IntegrityMethod.COUNT_DISTINCT,
            key="customer_id",
            watermark="updated_at",
            window=WindowSpec(
                op=WindowOp.BETWEEN,
                start="2026-02-15 00:00:00",
                end="2026-02-16 23:59:59",
            ),
        )
    ]

    findings = run_syncs(pipelines, sources=sources)
    assert len(findings) == 1
    assert findings[0].details["method"] == "count_distinct"


def test_integrity_hash_mismatch(tmp_path):
    source_path = tmp_path / "source.duckdb"
    target_path = tmp_path / "target.duckdb"
    source_rows = [
        (1, 1, 99.99, "2026-02-16 10:00:00"),
        (2, 2, 49.50, "2026-02-16 11:00:00"),
    ]
    target_rows = [
        (1, 1, 99.99, "2026-02-16 10:00:00"),
        (2, 2, 50.00, "2026-02-16 11:00:00"),
    ]
    _create_orders_db(source_path, source_rows)
    _create_orders_db(target_path, target_rows)

    sources = {
        "source": f"duckdb:///{source_path}",
        "target": f"duckdb:///{target_path}",
    }

    pipelines = [
        Sync(
            name="orders_hash",
            source="source",
            target="target",
            source_table="main.orders",
            target_table="main.orders",
            method=IntegrityMethod.HASH,
            key="id",
            hash_columns=["id", "amount", "updated_at"],
            watermark="updated_at",
            window=WindowSpec(
                op=WindowOp.BETWEEN,
                start="2026-02-16 00:00:00",
                end="2026-02-16 23:59:59",
            ),
        )
    ]

    findings = run_syncs(pipelines, sources=sources)
    assert len(findings) == 1
    assert findings[0].details["method"] == "hash"


def test_integrity_target_max_watermark_tolerance(tmp_path):
    source_path = tmp_path / "source.duckdb"
    target_path = tmp_path / "target.duckdb"
    source_rows = [
        (1, 1, 99.99, "2026-02-16 10:00:00"),
        (2, 2, 49.50, "2026-02-16 11:00:00"),
        (3, 3, 25.00, "2026-02-17 09:00:00"),
    ]
    target_rows = [
        (1, 1, 99.99, "2026-02-16 10:00:00"),
        (2, 2, 49.50, "2026-02-16 11:00:00"),
    ]
    _create_orders_db(source_path, source_rows)
    _create_orders_db(target_path, target_rows)

    sources = {
        "source": f"duckdb:///{source_path}",
        "target": f"duckdb:///{target_path}",
    }

    pipelines = [
        Sync(
            name="orders_tolerance",
            source="source",
            target="target",
            source_table="main.orders",
            target_table="main.orders",
            method=IntegrityMethod.COUNT,
            watermark="updated_at",
            window=WindowSpec(
                op=WindowOp.BETWEEN,
                start="2026-02-16 00:00:00",
                end="2026-02-17 23:59:59",
            ),
            tolerance_mode="target_max_watermark",
        )
    ]

    findings = run_syncs(pipelines, sources=sources)
    assert not findings


# --- Validation error tests ---


def test_sources_none_raises():
    pipeline = Sync(
        name="p",
        source="s",
        target="t",
        source_table="a.b",
        target_table="a.b",
        method=IntegrityMethod.COUNT,
        watermark="ts",
        window=WindowSpec(op=WindowOp.BETWEEN, start="2026-01-01", end="2026-01-02"),
    )
    with pytest.raises(ValueError, match="sources"):
        run_syncs([pipeline], sources=None)


def test_unknown_source_raises():
    pipeline = Sync(
        name="p",
        source="missing",
        target="also_missing",
        source_table="a.b",
        target_table="a.b",
        method=IntegrityMethod.COUNT,
        watermark="ts",
        window=WindowSpec(op=WindowOp.BETWEEN, start="2026-01-01", end="2026-01-02"),
    )
    with pytest.raises(ValueError, match="unknown sources"):
        run_syncs([pipeline], sources={"other": "duckdb:///x"})


def test_missing_window_raises():
    pipeline = Sync(
        name="p",
        source="s",
        target="t",
        source_table="a.b",
        target_table="a.b",
        method=IntegrityMethod.COUNT,
        watermark="ts",
        window=None,
    )
    with pytest.raises(ValueError, match="missing a window"):
        run_syncs([pipeline], sources={"s": "duckdb:///x", "t": "duckdb:///y"})


def test_missing_watermark_raises():
    pipeline = Sync(
        name="p",
        source="s",
        target="t",
        source_table="a.b",
        target_table="a.b",
        method=IntegrityMethod.COUNT,
        watermark=None,
        window=WindowSpec(op=WindowOp.BETWEEN, start="2026-01-01", end="2026-01-02"),
    )
    with pytest.raises(ValueError, match="missing a watermark"):
        run_syncs([pipeline], sources={"s": "duckdb:///x", "t": "duckdb:///y"})


@pytest.mark.parametrize(
    "method", [IntegrityMethod.PK, IntegrityMethod.COUNT_DISTINCT, IntegrityMethod.HASH]
)
def test_key_required_for_method(method):
    pipeline = Sync(
        name="p",
        source="s",
        target="t",
        source_table="a.b",
        target_table="a.b",
        method=method,
        key=None,
        watermark="ts",
        window=WindowSpec(op=WindowOp.BETWEEN, start="2026-01-01", end="2026-01-02"),
    )
    with pytest.raises(ValueError, match="requires a key"):
        run_syncs([pipeline], sources={"s": "duckdb:///x", "t": "duckdb:///y"})


# --- PK method test ---


def test_integrity_pk_mismatch(tmp_path):
    source_path = tmp_path / "source.duckdb"
    target_path = tmp_path / "target.duckdb"
    source_rows = [
        (1, 1, 99.99, "2026-02-16 10:00:00"),
        (2, 2, 49.50, "2026-02-16 11:00:00"),
        (3, 3, 25.00, "2026-02-16 09:00:00"),
    ]
    target_rows = [
        (1, 1, 99.99, "2026-02-16 10:00:00"),
        (2, 2, 49.50, "2026-02-16 11:00:00"),
    ]
    _create_orders_db(source_path, source_rows)
    _create_orders_db(target_path, target_rows)

    sources = {
        "source": f"duckdb:///{source_path}",
        "target": f"duckdb:///{target_path}",
    }

    pipelines = [
        Sync(
            name="orders_pk",
            source="source",
            target="target",
            source_table="main.orders",
            target_table="main.orders",
            method=IntegrityMethod.PK,
            key="id",
            watermark="updated_at",
            window=WindowSpec(
                op=WindowOp.BETWEEN,
                start="2026-02-16 00:00:00",
                end="2026-02-16 23:59:59",
            ),
        )
    ]

    findings = run_syncs(pipelines, sources=sources)
    assert len(findings) == 1
    assert findings[0].details["method"] == "pk"


# --- Hash edge cases ---


def test_integrity_hash_defaults_to_key(tmp_path):
    """hash_columns=None defaults to [key]; same data -> no finding."""
    source_path = tmp_path / "source.duckdb"
    rows = [
        (1, 1, 99.99, "2026-02-16 10:00:00"),
        (2, 2, 49.50, "2026-02-16 11:00:00"),
    ]
    _create_orders_db(source_path, rows)

    sources = {
        "source": f"duckdb:///{source_path}",
        "target": f"duckdb:///{source_path}",
    }

    pipelines = [
        Sync(
            name="orders_hash_default",
            source="source",
            target="target",
            source_table="main.orders",
            target_table="main.orders",
            method=IntegrityMethod.HASH,
            key="id",
            hash_columns=None,
            watermark="updated_at",
            window=WindowSpec(
                op=WindowOp.BETWEEN,
                start="2026-02-16 00:00:00",
                end="2026-02-16 23:59:59",
            ),
        )
    ]

    findings = run_syncs(pipelines, sources=sources)
    assert not findings
