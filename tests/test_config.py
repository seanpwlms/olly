import pytest

from olly.config import (
    ConfigError,
    ConnectionConfig,
    CostConfig,
    DbtConfig,
    IntegrityConfig,
    NamedConnection,
    OllyConfig,
    Override,
    Selection,
    Settings,
    SlackConfig,
    UsageConfig,
    load_config,
    write_config,
)
from olly.config_ops import validate_config


def _make_config(
    connection: ConnectionConfig | None = None,
    selection: Selection | None = None,
    overrides: list[Override] | None = None,
    **kwargs,
) -> OllyConfig:
    """Helper to build an OllyConfig with a single 'primary' connection."""
    conn = connection or ConnectionConfig(type="duckdb", path="x.duckdb")
    nc = NamedConnection(
        name="primary",
        connection=conn,
        selection=selection or Selection(),
        overrides=overrides or [],
    )
    return OllyConfig(connections={"primary": nc}, **kwargs)


def test_write_and_load_roundtrip(tmp_path):
    nc = NamedConnection(
        name="primary",
        connection=ConnectionConfig(type="duckdb", path="my.duckdb"),
        selection=Selection(
            include_schemas=["main"],
            exclude_schemas=["scratch"],
            include_tables=["main.*"],
            exclude_tables=["main._temp"],
        ),
        overrides=[
            Override(
                match="main.orders",
                freshness_column="updated_at",
                freshness_threshold_hours=12,
            ),
        ],
    )
    config = OllyConfig(
        connections={"primary": nc},
        sources={
            "prod": "postgres://example/db",
            "analytics": "bigquery://proj.dataset",
        },
        integrity=IntegrityConfig(module="pipelines.py"),
        settings=Settings(
            history_depth=10,
            volume_zscore_threshold=2.5,
        ),
    )

    path = tmp_path / "olly.toml"
    write_config(config, path)
    loaded = load_config(path)

    assert loaded.connections["primary"].connection.type == "duckdb"
    assert loaded.connections["primary"].connection.path == "my.duckdb"
    assert loaded.settings.history_depth == 10
    assert loaded.settings.volume_zscore_threshold == 2.5
    assert loaded.connections["primary"].selection.include_schemas == ["main"]
    assert loaded.connections["primary"].selection.exclude_schemas == ["scratch"]
    assert loaded.connections["primary"].selection.include_tables == ["main.*"]
    assert loaded.connections["primary"].selection.exclude_tables == ["main._temp"]
    assert len(loaded.connections["primary"].overrides) == 1
    assert loaded.connections["primary"].overrides[0].match == "main.orders"
    assert loaded.connections["primary"].overrides[0].freshness_column == "updated_at"
    assert loaded.sources["prod"] == "postgres://example/db"
    assert loaded.integrity.module == "pipelines.py"


def test_load_config_defaults(tmp_path):
    """Settings not in file should get defaults."""
    path = tmp_path / "olly.toml"
    config = _make_config(
        connection=ConnectionConfig(type="duckdb", path="x.duckdb"),
    )
    write_config(config, path)
    loaded = load_config(path)

    assert loaded.settings.history_depth == 30
    assert loaded.settings.volume_zscore_threshold == 3.0
    assert loaded.settings.freshness_threshold_hours == 24.0
    assert loaded.settings.min_history_for_anomaly == 5
    assert loaded.settings.write_results is True
    assert loaded.connections["primary"].selection.include_schemas == ["*"]
    assert loaded.connections["primary"].selection.exclude_schemas == [
        "information_schema"
    ]
    assert loaded.connections["primary"].selection.include_tables == ["*.*"]
    assert loaded.connections["primary"].selection.exclude_tables == []
    assert loaded.sources == {}
    assert loaded.integrity.module is None


# --- TOML schema validation tests ---


def test_load_config_missing_connection(tmp_path):
    """Missing [connections] table raises ConfigError."""
    path = tmp_path / "olly.toml"
    path.write_text("[settings]\nhistory_depth = 10\n")
    with pytest.raises(ConfigError, match="Missing required key 'connections'"):
        load_config(path)


def test_load_config_missing_type(tmp_path):
    """Missing type inside [connections.primary] raises ConfigError."""
    path = tmp_path / "olly.toml"
    path.write_text('[connections.primary]\npath = "x.duckdb"\n')
    with pytest.raises(ConfigError, match="Missing required key 'type'"):
        load_config(path)


def test_load_config_invalid_toml(tmp_path):
    """Malformed TOML raises ConfigError."""
    path = tmp_path / "olly.toml"
    path.write_bytes(b"[connection\n")
    with pytest.raises(ConfigError, match="Invalid TOML"):
        load_config(path)


def test_load_config_missing_override_match(tmp_path):
    """Missing match in override raises ConfigError."""
    path = tmp_path / "olly.toml"
    path.write_text(
        '[connections.primary]\ntype = "duckdb"\npath = "x.duckdb"\n'
        "[[connections.primary.overrides]]\n"
        'freshness_column = "updated_at"\n'
    )
    with pytest.raises(ConfigError, match="Missing required key 'match'"):
        load_config(path)


# --- Usage config tests ---


def test_load_usage_config(tmp_path):
    """Usage config section should parse correctly."""
    path = tmp_path / "olly.toml"
    path.write_text(
        '[connections.primary]\ntype = "duckdb"\npath = "x.duckdb"\n'
        "\n[usage]\n"
        "enabled = true\n"
        "lookback_days = 60\n"
        "unused_threshold_days = 14\n"
        'bigquery_region = "eu"\n'
    )
    config = load_config(path)
    assert config.usage.enabled is True
    assert config.usage.lookback_days == 60
    assert config.usage.unused_threshold_days == 14
    assert config.usage.bigquery_region == "eu"


def test_usage_config_defaults(tmp_path):
    """Usage config should have sensible defaults when section is absent."""
    path = tmp_path / "olly.toml"
    path.write_text('[connections.primary]\ntype = "duckdb"\npath = "x.duckdb"\n')
    config = load_config(path)
    assert config.usage.enabled is False
    assert config.usage.lookback_days == 90
    assert config.usage.unused_threshold_days == 30
    assert config.usage.bigquery_region == "us"


def test_validate_usage_lookback_less_than_threshold():
    """Validation should warn when lookback_days < unused_threshold_days."""
    config = _make_config(
        connection=ConnectionConfig(type="duckdb", path="x.duckdb"),
        usage=UsageConfig(
            enabled=True,
            lookback_days=20,
            unused_threshold_days=30,
        ),
    )
    warnings = validate_config(config)
    assert any("lookback_days must be >=" in w for w in warnings)


def test_write_config_with_dbt(tmp_path):
    """write_config serializes dbt section correctly."""
    config = _make_config(
        connection=ConnectionConfig(type="duckdb", path="x.duckdb"),
        dbt=DbtConfig(
            run_results_path="target/run_results.json",
            include_skipped=True,
        ),
    )
    path = tmp_path / "olly.toml"
    write_config(config, path)
    loaded = load_config(path)
    assert loaded.dbt.run_results_path == "target/run_results.json"
    assert loaded.dbt.include_skipped is True


def test_write_config_with_usage(tmp_path):
    """write_config serializes usage section correctly."""
    config = _make_config(
        connection=ConnectionConfig(type="duckdb", path="x.duckdb"),
        usage=UsageConfig(
            enabled=True,
            lookback_days=60,
            unused_threshold_days=14,
            bigquery_region="eu",
        ),
    )
    path = tmp_path / "olly.toml"
    write_config(config, path)
    loaded = load_config(path)
    assert loaded.usage.enabled is True
    assert loaded.usage.lookback_days == 60


def test_write_config_with_cost(tmp_path):
    """write_config serializes cost section correctly."""
    config = _make_config(
        connection=ConnectionConfig(type="duckdb", path="x.duckdb"),
        cost=CostConfig(
            enabled=True,
            lookback_days=14,
            bigquery_region="eu",
            price_per_tb_usd=5.0,
            spike_threshold=2.5,
        ),
    )
    path = tmp_path / "olly.toml"
    write_config(config, path)
    loaded = load_config(path)
    assert loaded.cost.enabled is True
    assert loaded.cost.lookback_days == 14
    assert loaded.cost.price_per_tb_usd == 5.0
    assert loaded.cost.spike_threshold == 2.5


def test_load_cost_config(tmp_path):
    """Cost config section should parse correctly."""
    path = tmp_path / "olly.toml"
    path.write_text(
        '[connections.primary]\ntype = "duckdb"\npath = "x.duckdb"\n'
        "\n[cost]\n"
        "enabled = true\n"
        "lookback_days = 14\n"
        'bigquery_region = "eu"\n'
        "price_per_tb_usd = 5.0\n"
        "spike_threshold = 2.5\n"
    )
    config = load_config(path)
    assert config.cost.enabled is True
    assert config.cost.lookback_days == 14
    assert config.cost.bigquery_region == "eu"
    assert config.cost.price_per_tb_usd == 5.0
    assert config.cost.spike_threshold == 2.5


def test_cost_config_defaults(tmp_path):
    """Cost config should have sensible defaults when section is absent."""
    path = tmp_path / "olly.toml"
    path.write_text('[connections.primary]\ntype = "duckdb"\npath = "x.duckdb"\n')
    config = load_config(path)
    assert config.cost.enabled is False
    assert config.cost.lookback_days == 30
    assert config.cost.bigquery_region == "us"
    assert config.cost.price_per_tb_usd == 6.25
    assert config.cost.spike_threshold == 3.0


# --- Connection extras tests ---


def test_extras_parsed_from_toml(tmp_path):
    """Unknown keys in [connections.primary] are collected into extras."""
    path = tmp_path / "olly.toml"
    path.write_text(
        '[connections.primary]\ntype = "snowflake"\naccount = "myaccount"\n'
        'user = "admin"\nrole = "ANALYST"\nwarehouse = "COMPUTE_WH"\n'
    )
    config = load_config(path)
    assert config.connections["primary"].connection.extras == {
        "user": "admin",
        "role": "ANALYST",
        "warehouse": "COMPUTE_WH",
    }


def test_extras_roundtrip(tmp_path):
    """Extras survive write_config -> load_config round-trip."""
    nc = NamedConnection(
        name="primary",
        connection=ConnectionConfig(
            type="snowflake",
            account="myaccount",
            extras={"user": "admin", "role": "ANALYST"},
        ),
    )
    config = OllyConfig(connections={"primary": nc})
    path = tmp_path / "olly.toml"
    write_config(config, path)
    loaded = load_config(path)
    assert loaded.connections["primary"].connection.extras["user"] == "admin"
    assert loaded.connections["primary"].connection.extras["role"] == "ANALYST"


def test_no_extras_empty_dict(tmp_path):
    """When no unknown keys exist, extras is an empty dict."""
    path = tmp_path / "olly.toml"
    path.write_text('[connections.primary]\ntype = "duckdb"\npath = "x.duckdb"\n')
    config = load_config(path)
    assert config.connections["primary"].connection.extras == {}


# --- state_schema tests ---


def test_state_schema_default(tmp_path):
    """state_schema defaults to None when not set."""
    path = tmp_path / "olly.toml"
    path.write_text('[connections.primary]\ntype = "duckdb"\npath = "x.duckdb"\n')
    config = load_config(path)
    assert config.settings.state_schema is None


def test_state_schema_parsed(tmp_path):
    """state_schema is read from TOML."""
    path = tmp_path / "olly.toml"
    path.write_text(
        '[connections.primary]\ntype = "duckdb"\npath = "x.duckdb"\n'
        '\n[settings]\nstate_schema = "_olly"\n'
    )
    config = load_config(path)
    assert config.settings.state_schema == "_olly"


def test_state_schema_roundtrip(tmp_path):
    """state_schema survives write_config -> load_config."""
    config = _make_config(
        connection=ConnectionConfig(type="duckdb", path="x.duckdb"),
        settings=Settings(state_schema="_olly"),
    )
    path = tmp_path / "olly.toml"
    write_config(config, path)
    loaded = load_config(path)
    assert loaded.settings.state_schema == "_olly"


def test_state_schema_none_not_written(tmp_path):
    """state_schema=None should not appear in written TOML."""
    config = _make_config(
        connection=ConnectionConfig(type="duckdb", path="x.duckdb"),
    )
    path = tmp_path / "olly.toml"
    write_config(config, path)
    content = path.read_text()
    assert "state_schema" not in content


# --- Slack config tests ---


def test_slack_config_defaults(tmp_path):
    """Slack config has sensible defaults when section is absent."""
    path = tmp_path / "olly.toml"
    path.write_text('[connections.primary]\ntype = "duckdb"\npath = "x.duckdb"\n')
    config = load_config(path)
    assert config.slack.webhook_url is None
    assert config.slack.on_error is True
    assert config.slack.on_warning is False


def test_load_slack_config(tmp_path):
    """Slack config section parses correctly."""
    path = tmp_path / "olly.toml"
    path.write_text(
        '[connections.primary]\ntype = "duckdb"\npath = "x.duckdb"\n'
        "\n[slack]\n"
        'webhook_url = "https://hooks.slack.com/services/T/B/x"\n'
        "on_error = true\n"
        "on_warning = true\n"
    )
    config = load_config(path)
    assert config.slack.webhook_url == "https://hooks.slack.com/services/T/B/x"
    assert config.slack.on_error is True
    assert config.slack.on_warning is True


def test_write_config_with_slack(tmp_path):
    """write_config serializes slack section when webhook_url is set."""
    config = _make_config(
        connection=ConnectionConfig(type="duckdb", path="x.duckdb"),
        slack=SlackConfig(
            webhook_url="https://hooks.slack.com/services/T/B/x",
            on_error=True,
            on_warning=True,
        ),
    )
    path = tmp_path / "olly.toml"
    write_config(config, path)
    loaded = load_config(path)
    assert loaded.slack.webhook_url == "https://hooks.slack.com/services/T/B/x"
    assert loaded.slack.on_warning is True


def test_write_config_slack_omitted_without_webhook(tmp_path):
    """write_config omits [slack] section when webhook_url is None."""
    config = _make_config(
        connection=ConnectionConfig(type="duckdb", path="x.duckdb"),
    )
    path = tmp_path / "olly.toml"
    write_config(config, path)
    content = path.read_text()
    assert "slack" not in content
