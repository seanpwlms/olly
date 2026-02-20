from olly.adapter import connect_typed
from olly.checks.freshness import check_freshness
from olly.checks.schema import check_schema
from olly.checks.volume import check_volume
from olly.config import ResolvedTableSettings, Settings
from olly.models import ColumnInfo, TableInfo, VolumeRecord


# --- Schema checks ---


def _make_table(name, columns, table_type="TABLE", schema="main"):
    return TableInfo(
        schema_name=schema,
        table_name=name,
        table_type=table_type,
        columns=[ColumnInfo(*c) for c in columns],
    )


def test_schema_no_changes():
    tables = [_make_table("t", [("id", "int32", False)])]
    findings = check_schema(tables, tables)
    assert findings == []


def test_schema_new_table():
    baseline = [_make_table("t1", [("id", "int32", False)])]
    current = baseline + [_make_table("t2", [("id", "int32", False)])]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "table_added"
    assert findings[0].table_name == "t2"


def test_schema_removed_table():
    baseline = [
        _make_table("t1", [("id", "int32", False)]),
        _make_table("t2", [("id", "int32", False)]),
    ]
    current = [_make_table("t1", [("id", "int32", False)])]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "table_removed"
    assert findings[0].severity == "error"


def test_schema_new_column():
    baseline = [_make_table("t", [("id", "int32", False)])]
    current = [_make_table("t", [("id", "int32", False), ("name", "string", True)])]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "column_added"
    assert findings[0].details["column"] == "name"


def test_schema_removed_column():
    baseline = [_make_table("t", [("id", "int32", False), ("name", "string", True)])]
    current = [_make_table("t", [("id", "int32", False)])]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "column_removed"
    assert findings[0].severity == "error"


def test_schema_type_changed():
    baseline = [_make_table("t", [("id", "int32", False)])]
    current = [_make_table("t", [("id", "int64", False)])]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "type_changed"
    assert findings[0].severity == "error"


def test_schema_nullability_changed():
    baseline = [_make_table("t", [("id", "int32", False)])]
    current = [_make_table("t", [("id", "int32", True)])]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "nullability_changed"


def test_schema_materialization_changed():
    baseline = [_make_table("t", [("id", "int32", False)], table_type="TABLE")]
    current = [_make_table("t", [("id", "int32", False)], table_type="VIEW")]
    findings = check_schema(current, baseline)

    assert len(findings) == 1
    assert findings[0].details["change"] == "materialization_changed"


# --- Volume checks ---


def test_volume_no_anomaly(state_db):
    # Build stable history
    for count in [100, 102, 98, 101, 99]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [VolumeRecord("main", "t", count)])

    current = [VolumeRecord("main", "t", 103)]
    findings = check_volume(current, state_db, Settings())
    assert findings == []


def test_volume_anomaly_spike(state_db):
    for count in [100, 102, 98, 101, 99]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [VolumeRecord("main", "t", count)])

    # Huge spike
    current = [VolumeRecord("main", "t", 500)]
    findings = check_volume(current, state_db, Settings())
    assert len(findings) == 1
    assert findings[0].check_type == "volume"
    assert findings[0].details["z_score"] > 3.0


def test_volume_anomaly_drop(state_db):
    for count in [1000, 1010, 990, 1005, 995]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [VolumeRecord("main", "t", count)])

    current = [VolumeRecord("main", "t", 0)]
    findings = check_volume(current, state_db, Settings())
    assert len(findings) == 1
    assert findings[0].details["z_score"] < -3.0


def test_volume_insufficient_history(state_db):
    # Only 2 snapshots, below min_history_for_anomaly=5
    for count in [100, 200]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [VolumeRecord("main", "t", count)])

    current = [VolumeRecord("main", "t", 10000)]
    findings = check_volume(current, state_db, Settings())
    assert findings == []


def test_volume_custom_threshold(state_db):
    for count in [100, 102, 98, 101, 99]:
        sid = state_db.create_snapshot()
        state_db.store_volume_data(sid, [VolumeRecord("main", "t", count)])

    # Moderate spike — above threshold=1.0 but below default 3.0
    current = [VolumeRecord("main", "t", 110)]
    thresholds = {("main", "t"): 1.0}
    findings = check_volume(current, state_db, Settings(), thresholds=thresholds)
    assert len(findings) == 1


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
        state_db.store_volume_data(sid, [VolumeRecord("main", "t", 100)])

    nc = olly_config.connections["primary"]
    backend = connect_typed(nc.connection)
    findings = check_freshness(backend, tables, settings, {}, state_db)

    proxy = [f for f in findings if f.table_name == "t"]
    assert len(proxy) == 1
    assert "unchanged" in proxy[0].description
