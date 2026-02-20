"""Tests for config_ops: pattern matching, schema/table filtering, override resolution, validation."""

from olly.config import (
    ConnectionConfig,
    ContractsConfig,
    DbtConfig,
    IntegrityConfig,
    NamedConnection,
    OllyConfig,
    Override,
    Selection,
)
from olly.config_ops import (
    filter_table_infos,
    match_pattern,
    match_table_pattern,
    resolve_table_settings_with_sources,
    select_schema_names,
    validate_config,
)
from olly.models import TableInfo


def _config(**kwargs) -> OllyConfig:
    conn = kwargs.pop("connection", ConnectionConfig(type="duckdb", path="x.duckdb"))
    selection = kwargs.pop("selection", Selection())
    overrides = kwargs.pop("overrides", [])
    nc = NamedConnection(
        name="primary", connection=conn, selection=selection, overrides=overrides
    )
    kwargs.setdefault("connections", {"primary": nc})
    return OllyConfig(**kwargs)


# --- match_pattern ---


def test_match_pattern_wildcard():
    assert match_pattern("*", "anything") is True


def test_match_pattern_exact():
    assert match_pattern("main", "main") is True
    assert match_pattern("main", "other") is False


def test_match_pattern_glob():
    assert match_pattern("stg_*", "stg_orders") is True
    assert match_pattern("stg_*", "raw_orders") is False


# --- match_table_pattern ---


def test_match_table_pattern_no_dot():
    assert match_table_pattern("main", "main", "orders") is False


def test_match_table_pattern_basic():
    assert match_table_pattern("main.*", "main", "orders") is True
    assert match_table_pattern("main.orders", "main", "orders") is True
    assert match_table_pattern("main.orders", "main", "customers") is False


# --- select_schema_names ---


def test_select_schema_names_exclude():
    selection = Selection(
        include_schemas=["*"],
        exclude_schemas=["information_schema", "scratch"],
    )
    result = select_schema_names(
        selection, ["main", "scratch", "analytics", "information_schema"]
    )
    assert result == ["main", "analytics"]


# --- filter_table_infos ---


def test_filter_table_infos_exclude():
    selection = Selection(
        include_tables=["*.*"],
        exclude_tables=["main._temp"],
    )
    tables = [
        TableInfo(
            schema_name="main", table_name="orders", table_type="TABLE", columns=[]
        ),
        TableInfo(
            schema_name="main", table_name="_temp", table_type="TABLE", columns=[]
        ),
    ]
    result = filter_table_infos(selection, tables)
    assert len(result) == 1
    assert result[0].table_name == "orders"


# --- resolve_table_settings ---


def test_resolve_defaults():
    config = _config()
    nc = config.connections["primary"]
    ts = resolve_table_settings_with_sources(
        config.settings, nc.overrides, "main", "orders"
    )
    assert ts.freshness_column is None
    assert ts.freshness_threshold_hours == 24.0
    assert ts.volume_zscore_threshold == 3.0


def test_resolve_schema_override():
    config = _config(
        overrides=[
            Override(match="main", freshness_column="updated_at"),
        ],
    )
    nc = config.connections["primary"]
    ts = resolve_table_settings_with_sources(
        config.settings, nc.overrides, "main", "orders"
    )
    assert ts.freshness_column == "updated_at"


def test_resolve_pattern_override_table():
    config = _config(
        overrides=[
            Override(match="main.stg_*", volume_zscore_threshold=5.0),
        ],
    )
    nc = config.connections["primary"]
    ts = resolve_table_settings_with_sources(
        config.settings, nc.overrides, "main", "stg_orders"
    )
    assert ts.volume_zscore_threshold == 5.0


def test_resolve_pattern_override_schema():
    config = _config(
        overrides=[
            Override(match="stg_*", freshness_threshold_hours=48.0),
        ],
    )
    nc = config.connections["primary"]
    ts = resolve_table_settings_with_sources(
        config.settings, nc.overrides, "stg_data", "orders"
    )
    assert ts.freshness_threshold_hours == 48.0


def test_resolve_object_override():
    config = _config(
        overrides=[
            Override(
                match="main.orders",
                freshness_column="created_at",
                volume_zscore_threshold=2.0,
            ),
        ],
    )
    nc = config.connections["primary"]
    ts = resolve_table_settings_with_sources(
        config.settings, nc.overrides, "main", "orders"
    )
    assert ts.freshness_column == "created_at"
    assert ts.volume_zscore_threshold == 2.0


def test_resolve_precedence_object_wins():
    config = _config(
        overrides=[
            Override(match="main", freshness_column="schema_col"),
            Override(match="main.*", freshness_column="pattern_col"),
            Override(match="main.orders", freshness_column="object_col"),
        ],
    )
    nc = config.connections["primary"]
    resolved = resolve_table_settings_with_sources(
        config.settings, nc.overrides, "main", "orders"
    )
    assert resolved.freshness_column == "object_col"
    assert resolved.freshness_column_source == "object"


def test_resolve_with_sources_schema():
    config = _config(
        overrides=[
            Override(match="main", freshness_threshold_hours=12.0),
        ],
    )
    nc = config.connections["primary"]
    resolved = resolve_table_settings_with_sources(
        config.settings, nc.overrides, "main", "orders"
    )
    assert resolved.freshness_threshold_hours == 12.0
    assert resolved.freshness_threshold_hours_source == "schema"


def test_resolve_with_sources_pattern():
    config = _config(
        overrides=[
            Override(match="main.*", volume_zscore_threshold=5.0),
        ],
    )
    nc = config.connections["primary"]
    resolved = resolve_table_settings_with_sources(
        config.settings, nc.overrides, "main", "orders"
    )
    assert resolved.volume_zscore_threshold == 5.0
    assert resolved.volume_zscore_threshold_source == "pattern"


# --- validate_config ---


def test_validate_empty_include_schemas():
    config = _config(selection=Selection(include_schemas=[]))
    warnings = validate_config(config)
    assert any("include_schemas is empty" in w for w in warnings)


def test_validate_table_pattern_missing_dot():
    config = _config(selection=Selection(include_tables=["orders"]))
    warnings = validate_config(config)
    assert any("missing a schema prefix" in w for w in warnings)


def test_validate_override_empty_match():
    config = _config(overrides=[Override(match="")])
    warnings = validate_config(config)
    assert any("empty match pattern" in w for w in warnings)


def test_validate_override_multiple_dots():
    config = _config(overrides=[Override(match="a.b.c", freshness_column="x")])
    warnings = validate_config(config)
    assert any("multiple dots" in w for w in warnings)


def test_validate_override_no_fields():
    config = _config(overrides=[Override(match="main")])
    warnings = validate_config(config)
    assert any("no fields set" in w for w in warnings)


def test_validate_integrity_module_empty():
    config = _config(integrity=IntegrityConfig(module="  "))
    warnings = validate_config(config)
    assert any("integrity.module is set but empty" in w for w in warnings)


def test_validate_empty_contracts_module():
    config = _config(contracts=ContractsConfig(module="  "))
    warnings = validate_config(config)
    assert any("contracts.module is set but empty" in w for w in warnings)


def test_validate_dbt_path_missing(tmp_path):
    config = _config(
        dbt=DbtConfig(run_results_path=str(tmp_path / "nonexistent.json")),
    )
    warnings = validate_config(config)
    assert any("does not exist" in w for w in warnings)
