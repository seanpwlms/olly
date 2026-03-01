import pytest

from olly.adapter import connect_typed
from olly.checks.freshness import check_freshness
from olly.checks.schema import check_schema
from olly.checks.volume import check_volume
from olly.config import ResolvedTableSettings, Settings
from olly.models import ColumnInfo, TableInfo
from conftest import make_table, make_volume_record


# --- Schema checks ---


def test_schema_no_changes():
    tables = [make_table("t", [("id", "int32", False)])]
    findings = check_schema(tables, tables)
    assert findings == []


def test_schema_new_table():
    baseline = [make_table("t1", [("id", "int32", False)])]
    current = baseline + [make_table("t2", [("id", "int32", False)])]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "table_added"
    assert findings[0].table_name == "t2"


def test_schema_removed_table():
    baseline = [
        make_table("t1", [("id", "int32", False)]),
        make_table("t2", [("id", "int32", False)]),
    ]
    current = [make_table("t1", [("id", "int32", False)])]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "table_removed"
    assert findings[0].severity == "error"


def test_schema_new_column():
    baseline = [make_table("t", [("id", "int32", False)])]
    current = [make_table("t", [("id", "int32", False), ("name", "string", True)])]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "column_added"
    assert findings[0].details["column"] == "name"


def test_schema_removed_column():
    baseline = [make_table("t", [("id", "int32", False), ("name", "string", True)])]
    current = [make_table("t", [("id", "int32", False)])]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "column_removed"
    assert findings[0].severity == "error"


def test_schema_type_changed():
    baseline = [make_table("t", [("id", "int32", False)])]
    current = [make_table("t", [("id", "int64", False)])]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "type_changed"
    assert findings[0].severity == "error"


def test_schema_nullability_changed():
    baseline = [make_table("t", [("id", "int32", False)])]
    current = [make_table("t", [("id", "int32", True)])]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "nullability_changed"


def test_schema_materialization_changed():
    baseline = [make_table("t", [("id", "int32", False)], table_type="TABLE")]
    current = [make_table("t", [("id", "int32", False)], table_type="VIEW")]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "materialization_changed"


def test_schema_multiple_changes_same_table():
    """Multiple changes on one table should produce multiple findings."""
    baseline = [make_table("orders", [
        ("id", "int32", False),
        ("customer_id", "int32", False),
        ("amount", "float64", False),
    ])]
    current = [make_table("orders", [
        ("id", "int64", False),  # Type changed
        ("customer_id", "int32", False),
        ("status", "string", True),  # New column (amount removed)
    ])]
    findings = check_schema(current, baseline)

    # Should have 3 findings: type change, column removed, column added
    assert len(findings) == 3

    changes = {f.details["change"] for f in findings}
    assert changes == {"type_changed", "column_removed", "column_added"}

    # Verify specific details
    type_change = [f for f in findings if f.details["change"] == "type_changed"][0]
    assert type_change.details["column"] == "id"
    assert type_change.details["old_type"] == "int32"
    assert type_change.details["new_type"] == "int64"

    removed = [f for f in findings if f.details["change"] == "column_removed"][0]
    assert removed.details["column"] == "amount"

    added = [f for f in findings if f.details["change"] == "column_added"][0]
    assert added.details["column"] == "status"


def test_schema_special_characters():
    """Tables and columns with special characters should be handled."""
    baseline = [make_table("my-table", [("user's_name", "string", True)])]
    current = [make_table("my-table", [("user's_name", "string", False)])]

    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "nullability_changed"
    assert findings[0].table_name == "my-table"
    assert findings[0].details["column"] == "user's_name"


def test_schema_column_order_changes():
    """Column order changes should not trigger findings (order doesn't matter)."""
    baseline = [make_table("t", [
        ("id", "int32", False),
        ("name", "string", True),
        ("email", "string", True),
    ])]
    current = [make_table("t", [
        ("email", "string", True),  # Reordered
        ("id", "int32", False),
        ("name", "string", True),
    ])]

    findings = check_schema(current, baseline)

    # Column order doesn't matter - no changes
    assert findings == []


# --- Volume checks ---


def test_volume_no_anomaly(state_db):
    # Build stable history
    for count in [100, 102, 98, 101, 99]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [make_volume_record("main", "t",count)])

    current = [make_volume_record("main", "t",103)]
    findings = check_volume(current, state_db, Settings())
    assert findings == []


def test_volume_anomaly_spike(state_db):
    for count in [100, 102, 98, 101, 99]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [make_volume_record("main", "t",count)])

    # Huge spike
    current = [make_volume_record("main", "t",500)]
    findings = check_volume(current, state_db, Settings())
    assert len(findings) == 1
    assert findings[0].check_type == "volume"
    assert findings[0].details["z_score"] > 3.0


def test_volume_anomaly_drop(state_db):
    for count in [1000, 1010, 990, 1005, 995]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [make_volume_record("main", "t",count)])

    current = [make_volume_record("main", "t",0)]
    findings = check_volume(current, state_db, Settings())
    assert len(findings) == 1
    assert findings[0].details["z_score"] < -3.0


def test_volume_insufficient_history(state_db):
    # Only 2 snapshots, below min_history_for_anomaly=5
    for count in [100, 200]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [make_volume_record("main", "t",count)])

    current = [make_volume_record("main", "t",10000)]
    findings = check_volume(current, state_db, Settings())
    assert findings == []


def test_volume_custom_threshold(state_db):
    for count in [100, 102, 98, 101, 99]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [make_volume_record("main", "t",count)])

    # Moderate spike — above threshold=1.0 but below default 3.0
    current = [make_volume_record("main", "t",110)]
    thresholds = {("main", "t"): 1.0}
    findings = check_volume(current, state_db, Settings(), thresholds=thresholds)
    assert len(findings) == 1


def test_volume_constant_history(state_db):
    """Constant row counts (std dev = 0) should not crash or trigger false positives."""
    # Create 5 snapshots with identical counts
    for _ in range(5):
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [make_volume_record("main", "t",100)])

    # Same count again - should not trigger anomaly (std dev = 0 -> can't calculate z-score)
    current = [make_volume_record("main", "t",100)]
    findings = check_volume(current, state_db, Settings())
    assert findings == []


def test_volume_edge_of_insufficient_history(state_db):
    """4 snapshots when min_history=5 should skip anomaly detection."""
    # Only 4 historical snapshots
    for count in [100, 101, 99, 102]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [make_volume_record("main", "t",count)])

    # Huge spike that would normally trigger
    current = [make_volume_record("main", "t",10000)]
    findings = check_volume(current, state_db, Settings(min_history_for_anomaly=5))
    # Should skip detection due to insufficient history
    assert findings == []


def test_volume_exactly_sufficient_history(state_db):
    """Exactly min_history snapshots should enable anomaly detection."""
    # Exactly 5 snapshots (the default threshold)
    for count in [100, 102, 98, 101, 99]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [make_volume_record("main", "t",count)])

    # Huge spike should trigger with exactly min_history
    current = [make_volume_record("main", "t",500)]
    findings = check_volume(current, state_db, Settings(min_history_for_anomaly=5))
    assert len(findings) == 1
    assert findings[0].details["z_score"] > 3.0


def test_volume_empty_history(state_db):
    """New table with no history should not trigger anomaly."""
    current = [make_volume_record("main", "new_table",1000)]
    findings = check_volume(current, state_db, Settings())
    assert findings == []


def test_volume_all_zeros(state_db):
    """History of all zeros with current zero should not crash."""
    for _ in range(5):
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [make_volume_record("main", "t",0)])

    current = [make_volume_record("main", "t",0)]
    findings = check_volume(current, state_db, Settings())
    # Should not crash or trigger anomaly (std dev = 0)
    assert findings == []


def test_volume_zero_to_nonzero(state_db):
    """Going from zero rows to nonzero triggers anomaly (infinite z-score)."""
    for _ in range(5):
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [make_volume_record("main", "t",0)])

    # First data appears - triggers anomaly because std dev = 0
    current = [make_volume_record("main", "t",100)]
    findings = check_volume(current, state_db, Settings())
    # Any deviation from constant history (std dev = 0) produces infinite z-score
    assert len(findings) == 1
    assert findings[0].check_type == "volume"
    # Z-score will be very large (approaching infinity)
    assert findings[0].details["z_score"] > 1000


# --- Freshness checks (integration with Ibis) ---


def test_freshness_timestamp_stale(olly_config_with_freshness, state_db):
    """Orders have timestamps from Feb 16 — with a 0-hour threshold, they're stale."""
    config = olly_config_with_freshness
    nc = config.connections["primary"]
    # Set an impossibly tight threshold
    nc.overrides[0].freshness_threshold_hours = 0.0001

    backend = connect_typed(nc.connection)
    tables = backend.fetch_schema_info(["main"])
    overrides_map = {
        ("main", "orders"): ResolvedTableSettings(
            freshness_column="updated_at",
            freshness_threshold_hours=0.0001,
            volume_zscore_threshold=config.settings.volume_zscore_threshold,
            freshness_column_source="object",
            freshness_threshold_hours_source="object",
            volume_zscore_threshold_source="global",
        )
    }

    findings = check_freshness(
        backend, tables, config.settings, overrides_map, state_db
    )

    stale = [
        f for f in findings if f.check_type == "freshness" and "orders" in f.table_name
    ]
    assert len(stale) == 1
    assert "Stale data" in stale[0].description


def test_freshness_timestamp_fresh(olly_config_with_freshness, state_db):
    """With a huge threshold, orders should be fine."""
    config = olly_config_with_freshness
    nc = config.connections["primary"]
    nc.overrides[0].freshness_threshold_hours = 999999

    backend = connect_typed(nc.connection)
    tables = backend.fetch_schema_info(["main"])
    overrides_map = {
        ("main", "orders"): ResolvedTableSettings(
            freshness_column="updated_at",
            freshness_threshold_hours=999999,
            volume_zscore_threshold=config.settings.volume_zscore_threshold,
            freshness_column_source="object",
            freshness_threshold_hours_source="object",
            volume_zscore_threshold_source="global",
        )
    }

    findings = check_freshness(
        backend, tables, config.settings, overrides_map, state_db
    )
    stale = [
        f for f in findings if f.check_type == "freshness" and "orders" in f.table_name
    ]
    assert stale == []


def test_freshness_staleness_proxy(state_db, olly_config):
    """Tables without freshness_column use row-count-unchanged proxy."""
    tables = [
        TableInfo(
            schema_name="main",
            table_name="t",
            table_type="TABLE",
            columns=[ColumnInfo("id", "int32", False)],
        ),
    ]
    # Create enough unchanged snapshots
    settings = Settings(min_history_for_anomaly=3)
    for _ in range(5):
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [make_volume_record("main", "t",100)])

    nc = olly_config.connections["primary"]
    backend = connect_typed(nc.connection)
    findings = check_freshness(backend, tables, settings, {}, state_db)

    proxy = [f for f in findings if f.table_name == "t"]
    assert len(proxy) == 1
    assert "unchanged" in proxy[0].description


def test_freshness_missing_column(tmp_path, state_db):
    """Missing freshness column raises RuntimeError from the adapter."""
    import duckdb

    db_path = tmp_path / "missing_col_test.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE TABLE events (id INTEGER, name VARCHAR)")
    conn.execute("INSERT INTO events VALUES (1, 'test')")
    conn.close()

    from olly.adapters.duckdb import DuckDBAdapter

    adapter = DuckDBAdapter(str(db_path))
    tables = adapter.fetch_schema_info(["main"])
    events_tables = [t for t in tables if t.table_name == "events"]

    overrides_map = {
        ("main", "events"): ResolvedTableSettings(
            freshness_column="occurred_at",  # Column doesn't exist!
            freshness_threshold_hours=24,
            volume_zscore_threshold=3.0,
            freshness_column_source="object",
            freshness_threshold_hours_source="object",
            volume_zscore_threshold_source="global",
        )
    }

    with pytest.raises(RuntimeError, match="Failed to fetch max timestamp"):
        check_freshness(adapter, events_tables, Settings(), overrides_map, state_db)


def test_freshness_future_timestamps(tmp_path, state_db):
    """Future timestamps should not crash the freshness check."""
    import duckdb
    from datetime import datetime, timedelta

    # Create table with future timestamp
    db_path = tmp_path / "future_test.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE TABLE events (id INTEGER, occurred_at TIMESTAMP)")
    future = datetime.now() + timedelta(days=365)
    conn.execute(f"INSERT INTO events VALUES (1, '{future.strftime('%Y-%m-%d %H:%M:%S')}')")
    conn.close()

    from olly.adapters.duckdb import DuckDBAdapter

    adapter = DuckDBAdapter(str(db_path))
    tables = adapter.fetch_schema_info(["main"])

    overrides_map = {
        ("main", "events"): ResolvedTableSettings(
            freshness_column="occurred_at",
            freshness_threshold_hours=24,
            volume_zscore_threshold=3.0,
            freshness_column_source="object",
            freshness_threshold_hours_source="object",
            volume_zscore_threshold_source="global",
        )
    }

    # Should not crash
    findings = check_freshness(adapter, tables, Settings(), overrides_map, state_db)

    # Future timestamp means data is "fresh" (not stale)
    stale = [f for f in findings if f.table_name == "events"]
    assert stale == []


def test_freshness_staleness_proxy_boundary(state_db, olly_config):
    """Staleness proxy triggers exactly at min_history threshold."""
    tables = [
        TableInfo(
            schema_name="main",
            table_name="t",
            table_type="TABLE",
            columns=[ColumnInfo("id", "int32", False)],
        ),
    ]

    # Create exactly min_history_for_anomaly unchanged snapshots
    settings = Settings(min_history_for_anomaly=5)
    for _ in range(5):
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [make_volume_record("main", "t",100)])

    nc = olly_config.connections["primary"]
    backend = connect_typed(nc.connection)
    findings = check_freshness(backend, tables, settings, {}, state_db)

    # Should trigger at exactly the threshold
    proxy = [f for f in findings if f.table_name == "t"]
    assert len(proxy) == 1


def test_freshness_staleness_proxy_no_trigger_with_changes(state_db, olly_config):
    """Staleness proxy does NOT trigger when row count varies."""
    tables = [
        TableInfo(
            schema_name="main",
            table_name="t",
            table_type="TABLE",
            columns=[ColumnInfo("id", "int32", False)],
        ),
    ]

    # Create snapshots with DIFFERENT counts
    settings = Settings(min_history_for_anomaly=3)
    for count in [100, 101, 99, 102, 98]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [make_volume_record("main", "t",count)])

    nc = olly_config.connections["primary"]
    backend = connect_typed(nc.connection)
    findings = check_freshness(backend, tables, settings, {}, state_db)

    # Should NOT trigger because counts are changing
    proxy = [f for f in findings if f.table_name == "t"]
    assert proxy == []
