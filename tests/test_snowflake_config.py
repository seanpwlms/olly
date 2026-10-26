from olly.adapter import connect_typed
from olly.config import (
    ConnectionConfig,
    NamedConnection,
    OllyConfig,
    Selection,
    load_config,
    write_config,
)


class TestConnectionConfigFields:
    def test_snowflake_defaults(self):
        conn = ConnectionConfig(type="snowflake", account="myaccount")
        assert conn.use_account_usage is False
        assert conn.database is None

    def test_snowflake_custom(self):
        conn = ConnectionConfig(
            type="snowflake",
            account="myaccount",
            database="mydb",
            use_account_usage=True,
        )
        assert conn.use_account_usage is True
        assert conn.database == "mydb"

    def test_bigquery_defaults(self):
        conn = ConnectionConfig(type="bigquery", project="myproj")
        # None defers to the adapter's own default.
        assert conn.use_information_schema_row_counts is None
        assert conn.dataset is None


class TestLoadConfig:
    def test_parses_snowflake(self, tmp_path):
        config_path = tmp_path / "olly.toml"
        config_path.write_text(
            '[connections.primary]\ntype = "snowflake"\naccount = "myaccount"\n'
            'database = "mydb"\nuse_account_usage = true\n'
        )
        config = load_config(config_path)
        assert config.connections["primary"].connection.type == "snowflake"
        assert config.connections["primary"].connection.account == "myaccount"
        assert config.connections["primary"].connection.database == "mydb"
        assert config.connections["primary"].connection.use_account_usage is True

    def test_defaults_snowflake(self, tmp_path):
        config_path = tmp_path / "olly.toml"
        config_path.write_text(
            '[connections.primary]\ntype = "snowflake"\naccount = "myaccount"\n'
        )
        config = load_config(config_path)
        assert config.connections["primary"].connection.use_account_usage is False
        assert config.connections["primary"].connection.database is None


class TestWriteConfigRoundTrip:
    def test_snowflake_settings(self, tmp_path):
        nc = NamedConnection(
            name="primary",
            connection=ConnectionConfig(
                type="snowflake",
                account="myaccount",
                database="mydb",
                use_account_usage=True,
            ),
            selection=Selection(),
        )
        config = OllyConfig(connections={"primary": nc})
        path = tmp_path / "olly.toml"
        write_config(config, path)
        loaded = load_config(path)
        assert loaded.connections["primary"].connection.type == "snowflake"
        assert loaded.connections["primary"].connection.account == "myaccount"
        assert loaded.connections["primary"].connection.database == "mydb"
        assert loaded.connections["primary"].connection.use_account_usage is True

    def test_row_count_flag_omitted_when_unset(self, tmp_path):
        nc = NamedConnection(
            name="primary",
            connection=ConnectionConfig(type="snowflake", account="a"),
            selection=Selection(),
        )
        path = tmp_path / "olly.toml"
        write_config(OllyConfig(connections={"primary": nc}), path)
        assert "use_information_schema_row_counts" not in path.read_text()
        loaded = load_config(path)
        assert loaded.connections["primary"].connection.use_information_schema_row_counts is None

    def test_row_count_flag_round_trips_for_postgres(self, tmp_path):
        nc = NamedConnection(
            name="primary",
            connection=ConnectionConfig(
                type="postgres",
                url="postgresql://h/db",
                use_information_schema_row_counts=True,
            ),
            selection=Selection(),
        )
        path = tmp_path / "olly.toml"
        write_config(OllyConfig(connections={"primary": nc}), path)
        loaded = load_config(path)
        assert loaded.connections["primary"].connection.use_information_schema_row_counts is True


def _capture_adapter(monkeypatch, target: str) -> list[dict]:
    """Replace the adapter class at *target* with one that records its kwargs."""
    constructed_with: list[dict] = []

    class FakeAdapter:
        def __init__(self, *args, **kwargs):
            constructed_with.append(kwargs)

    monkeypatch.setattr(target, FakeAdapter)
    return constructed_with


class TestRowCountFlagDefaults:
    def test_snowflake_defaults_to_metadata(self, monkeypatch):
        calls = _capture_adapter(monkeypatch, "olly.adapters.snowflake.SnowflakeAdapter")
        connect_typed(ConnectionConfig(type="snowflake", account="a"))
        assert calls[0]["use_information_schema_row_counts"] is True

    def test_snowflake_can_opt_out(self, monkeypatch):
        calls = _capture_adapter(monkeypatch, "olly.adapters.snowflake.SnowflakeAdapter")
        connect_typed(
            ConnectionConfig(
                type="snowflake", account="a", use_information_schema_row_counts=False
            )
        )
        assert calls[0]["use_information_schema_row_counts"] is False

    def test_bigquery_defaults_to_metadata(self, monkeypatch):
        calls = _capture_adapter(monkeypatch, "olly.adapters.bigquery.BigQueryAdapter")
        connect_typed(ConnectionConfig(type="bigquery", project="p"))
        assert calls[0]["use_information_schema_row_counts"] is True

    def test_postgres_defaults_to_count_star(self, monkeypatch):
        calls = _capture_adapter(monkeypatch, "olly.adapters.postgres.PostgresAdapter")
        connect_typed(ConnectionConfig(type="postgres", url="postgresql://h/db"))
        assert calls[0]["use_information_schema_row_counts"] is False

    def test_postgres_can_opt_in(self, monkeypatch):
        calls = _capture_adapter(monkeypatch, "olly.adapters.postgres.PostgresAdapter")
        connect_typed(
            ConnectionConfig(
                type="postgres",
                url="postgresql://h/db",
                use_information_schema_row_counts=True,
            )
        )
        assert calls[0]["use_information_schema_row_counts"] is True


class TestConnectDispatches:
    def test_snowflake(self, monkeypatch):
        constructed_with: list[dict] = []

        class FakeSnowflakeAdapter:
            def __init__(
                self, account, *, database=None, use_account_usage=False, **kwargs
            ):
                constructed_with.append(
                    {
                        "account": account,
                        "database": database,
                        "use_account_usage": use_account_usage,
                        **kwargs,
                    }
                )

        monkeypatch.setattr(
            "olly.adapters.snowflake.SnowflakeAdapter", FakeSnowflakeAdapter
        )
        conn = ConnectionConfig(
            type="snowflake",
            account="myaccount",
            database="mydb",
            use_account_usage=True,
        )
        connect_typed(conn)
        assert len(constructed_with) == 1
        assert constructed_with[0]["account"] == "myaccount"
        assert constructed_with[0]["database"] == "mydb"
        assert constructed_with[0]["use_account_usage"] is True

    def test_snowflake_extras_forwarded(self, monkeypatch):
        constructed_with: list[dict] = []

        class FakeSnowflakeAdapter:
            def __init__(
                self, account, *, database=None, use_account_usage=False, **kwargs
            ):
                constructed_with.append(
                    {
                        "account": account,
                        "database": database,
                        "use_account_usage": use_account_usage,
                        **kwargs,
                    }
                )

        monkeypatch.setattr(
            "olly.adapters.snowflake.SnowflakeAdapter", FakeSnowflakeAdapter
        )
        conn = ConnectionConfig(
            type="snowflake",
            account="myaccount",
            extras={"user": "admin", "role": "ANALYST", "warehouse": "COMPUTE_WH"},
        )
        connect_typed(conn)
        assert len(constructed_with) == 1
        assert constructed_with[0]["user"] == "admin"
        assert constructed_with[0]["role"] == "ANALYST"
        assert constructed_with[0]["warehouse"] == "COMPUTE_WH"
