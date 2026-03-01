from __future__ import annotations

import logging
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import tomli_w


logger = logging.getLogger(__name__)


@dataclass
class Selection:
    """Schema and table inclusion/exclusion filters."""

    include_schemas: list[str] = field(default_factory=lambda: ["*"])
    exclude_schemas: list[str] = field(default_factory=lambda: ["information_schema"])
    include_tables: list[str] = field(default_factory=lambda: ["*.*"])
    exclude_tables: list[str] = field(default_factory=list)


@dataclass
class Override:
    """Per-table or per-schema setting override matched by pattern."""

    match: str
    freshness_column: str | None = None
    freshness_threshold_hours: float | None = None
    volume_zscore_threshold: float | None = None
    volume_method: str | None = None


@dataclass
class ConnectionConfig:
    """Warehouse connection details."""

    type: str
    path: str | None = None  # duckdb
    url: str | None = None  # postgres
    project: str | None = None  # bigquery
    dataset: str | None = None  # bigquery
    region: str | None = None  # bigquery
    account: str | None = None  # snowflake
    database: str | None = None  # snowflake
    use_information_schema_row_counts: bool = True  # bigquery
    use_account_usage: bool = False  # snowflake
    extras: dict[str, Any] = field(default_factory=dict)


_KNOWN_CONN_KEYS = {
    "type",
    "path",
    "url",
    "project",
    "dataset",
    "region",
    "account",
    "database",
    "use_information_schema_row_counts",
    "use_account_usage",
    "connection_string",
}


@dataclass
class Settings:
    """Global default thresholds and behavior settings."""

    history_depth: int = 30
    volume_zscore_threshold: float = 3.0
    volume_method: str = "ewma"
    freshness_threshold_hours: float = 24.0
    min_history_for_anomaly: int = 5
    write_results: bool = True
    state_schema: str | None = None


@dataclass
class IntegrityConfig:
    """Configuration for cross-source data integrity pipelines."""

    module: str | None = None


@dataclass
class ContractsConfig:
    """Configuration for user-defined contract modules."""

    module: str | None = None


@dataclass
class DbtConfig:
    """Configuration for dbt run_results.json integration."""

    run_results_path: str | None = None
    include_skipped: bool = False


@dataclass
class UsageConfig:
    """Configuration for table usage/staleness monitoring."""

    enabled: bool = False
    lookback_days: int = 90
    unused_threshold_days: int = 30
    bigquery_region: str = "us"


@dataclass
class CostConfig:
    """Configuration for BigQuery query cost monitoring."""

    enabled: bool = False
    lookback_days: int = 30
    bigquery_region: str = "us"
    price_per_tb_usd: float = 6.25
    spike_threshold: float = 3.0


@dataclass
class SlackConfig:
    """Configuration for Slack webhook alerting."""

    webhook_url: str | None = None
    on_error: bool = True
    on_warning: bool = False


@dataclass
class NamedConnection:
    """A named connection bundling connection config, selection, and overrides."""

    name: str
    connection: ConnectionConfig
    selection: Selection = field(default_factory=Selection)
    overrides: list[Override] = field(default_factory=list)


@dataclass
class OllyConfig:
    """Top-level configuration parsed from ``olly.toml``."""

    connections: dict[str, NamedConnection] = field(default_factory=dict)
    settings: Settings = field(default_factory=Settings)
    integrity: IntegrityConfig = field(default_factory=IntegrityConfig)
    contracts: ContractsConfig = field(default_factory=ContractsConfig)
    dbt: DbtConfig = field(default_factory=DbtConfig)
    usage: UsageConfig = field(default_factory=UsageConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    config_path: Path | None = None


@dataclass
class ResolvedTableSettings:
    """Resolved per-table check settings with the source of each value."""

    freshness_column: str | None
    freshness_threshold_hours: float
    volume_zscore_threshold: float
    volume_method: str
    freshness_column_source: str
    freshness_threshold_hours_source: str
    volume_zscore_threshold_source: str
    volume_method_source: str


class ConfigError(Exception):
    """Raised when ``olly.toml`` is malformed or missing required fields."""


def _require(raw: dict, key: str, context: str) -> object:
    """Return ``raw[key]`` or raise :class:`ConfigError` with a clear message."""
    try:
        return raw[key]
    except KeyError:
        raise ConfigError(f"Missing required key '{key}' in {context}") from None


def _require_table(raw: dict, key: str, context: str) -> dict:
    """Like :func:`_require` but also asserts the value is a TOML table."""
    value = _require(raw, key, context)
    if not isinstance(value, dict):
        raise ConfigError(
            f"Expected a table for '{key}' in {context}, got {type(value).__name__}"
        )
    return value


def _parse_legacy_connection_string(cs: str) -> ConnectionConfig:
    """Convert a legacy ``connection_string`` value to a typed :class:`ConnectionConfig`."""
    if cs.startswith("duckdb:///"):
        return ConnectionConfig(type="duckdb", path=cs[len("duckdb:///") :] or None)
    if cs.startswith("duckdb://"):
        path = cs[len("duckdb://") :] or None
        return ConnectionConfig(type="duckdb", path=path)
    if cs.startswith("postgres://") or cs.startswith("postgresql://"):
        return ConnectionConfig(type="postgres", url=cs)
    if cs.startswith("bigquery://"):
        from urllib.parse import urlparse

        parsed = urlparse(cs)
        project = parsed.netloc or None
        dataset = parsed.path.lstrip("/") or None
        return ConnectionConfig(type="bigquery", project=project, dataset=dataset)
    if cs.startswith("snowflake://"):
        from urllib.parse import urlparse

        parsed = urlparse(cs)
        account = parsed.netloc or None
        database = parsed.path.lstrip("/") or None
        return ConnectionConfig(type="snowflake", account=account, database=database)
    raise ConfigError(f"Cannot parse legacy connection string: {cs}")


def load_config(path: Path | None = None) -> OllyConfig:
    """Load and parse an ``olly.toml`` configuration file.

    Args:
        path: Path to the TOML config file. Defaults to ``olly.toml`` in the
            current directory.

    Returns:
        Fully populated ``OllyConfig`` instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ConfigError: If the TOML file is malformed or missing required fields.
    """
    if path is None:
        path = Path("olly.toml")
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "rb") as f:
        try:
            raw = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc

    connections: dict[str, NamedConnection] = {}

    if "connections" in raw:
        conns_raw = _require_table(raw, "connections", "root")
        for conn_name, conn_section in conns_raw.items():
            if not isinstance(conn_section, dict):
                raise ConfigError(
                    f"Expected a table for connections.{conn_name}, "
                    f"got {type(conn_section).__name__}"
                )
            conn = _parse_connection_section(conn_section, f"[connections.{conn_name}]")
            sel = _parse_selection_section(conn_section.get("selection", {}))
            ovr = _parse_overrides_section(
                conn_section.get("overrides", []), f"connections.{conn_name}"
            )
            connections[conn_name] = NamedConnection(
                name=conn_name, connection=conn, selection=sel, overrides=ovr
            )
    elif "connection" in raw:
        conn_raw = _require_table(raw, "connection", "root")
        if "connection_string" in conn_raw and "type" not in conn_raw:
            logger.warning(
                "Deprecated: [connection] connection_string format. "
                "Use typed [connection] with type/path/url/project/account fields instead."
            )
            conn = _parse_legacy_connection_string(str(conn_raw["connection_string"]))
        else:
            conn = _parse_connection_section(conn_raw, "[connection]")
        sel = _parse_selection_section(raw.get("selection", {}))
        ovr = _parse_overrides_section(raw.get("overrides", []), "root")
        connections["primary"] = NamedConnection(
            name="primary", connection=conn, selection=sel, overrides=ovr
        )
    else:
        raise ConfigError("Missing required key 'connections' in root")

    settings_raw = raw.get("settings", {})
    # Drop legacy adapter settings subsections if present
    for _legacy_key in ("bigquery", "snowflake"):
        settings_raw.pop(_legacy_key, None)
    settings = Settings(
        history_depth=settings_raw.get("history_depth", 30),
        volume_zscore_threshold=settings_raw.get("volume_zscore_threshold", 3.0),
        volume_method=settings_raw.get("volume_method", "ewma"),
        freshness_threshold_hours=settings_raw.get("freshness_threshold_hours", 24.0),
        min_history_for_anomaly=settings_raw.get("min_history_for_anomaly", 5),
        write_results=settings_raw.get("write_results", True),
        state_schema=settings_raw.get("state_schema"),
    )

    integrity_raw = raw.get("integrity", {})
    integrity = IntegrityConfig(module=integrity_raw.get("module"))

    contracts_raw = raw.get("contracts", {})
    contracts = ContractsConfig(
        module=contracts_raw.get("module"),
    )

    dbt_raw = raw.get("dbt", {})
    dbt = DbtConfig(
        run_results_path=dbt_raw.get("run_results_path"),
        include_skipped=dbt_raw.get("include_skipped", False),
    )

    usage_raw = raw.get("usage", {})
    usage = UsageConfig(
        enabled=usage_raw.get("enabled", False),
        lookback_days=usage_raw.get("lookback_days", 90),
        unused_threshold_days=usage_raw.get("unused_threshold_days", 30),
        bigquery_region=usage_raw.get("bigquery_region", "us"),
    )

    cost_raw = raw.get("cost", {})
    cost = CostConfig(
        enabled=cost_raw.get("enabled", False),
        lookback_days=cost_raw.get("lookback_days", 30),
        bigquery_region=cost_raw.get("bigquery_region", "us"),
        price_per_tb_usd=cost_raw.get("price_per_tb_usd", 6.25),
        spike_threshold=cost_raw.get("spike_threshold", 3.0),
    )

    slack_raw = raw.get("slack", {})
    slack = SlackConfig(
        webhook_url=slack_raw.get("webhook_url"),
        on_error=slack_raw.get("on_error", True),
        on_warning=slack_raw.get("on_warning", False),
    )

    config = OllyConfig(
        connections=connections,
        settings=settings,
        integrity=integrity,
        contracts=contracts,
        dbt=dbt,
        usage=usage,
        cost=cost,
        slack=slack,
        config_path=path,
    )
    logger.debug("Loaded config from %s", path)
    return config


def _parse_connection_section(conn_raw: dict, context: str) -> ConnectionConfig:
    """Parse a connection section into a ConnectionConfig."""
    conn_type = str(_require(conn_raw, "type", context))
    extras = {
        k: v
        for k, v in conn_raw.items()
        if k not in _KNOWN_CONN_KEYS and k not in ("selection", "overrides")
    }
    return ConnectionConfig(
        type=conn_type,
        path=conn_raw.get("path"),
        url=conn_raw.get("url"),
        project=conn_raw.get("project"),
        dataset=conn_raw.get("dataset"),
        region=conn_raw.get("region"),
        account=conn_raw.get("account"),
        database=conn_raw.get("database"),
        use_information_schema_row_counts=conn_raw.get(
            "use_information_schema_row_counts", True
        ),
        use_account_usage=conn_raw.get("use_account_usage", False),
        extras=extras,
    )


def _parse_selection_section(selection_raw: dict) -> Selection:
    """Parse a selection section into a Selection."""
    return Selection(
        include_schemas=selection_raw.get("include_schemas", ["*"]),
        exclude_schemas=selection_raw.get("exclude_schemas", ["information_schema"]),
        include_tables=selection_raw.get("include_tables", ["*.*"]),
        exclude_tables=selection_raw.get("exclude_tables", []),
    )


def _parse_overrides_section(overrides_raw: list, context: str) -> list[Override]:
    """Parse an overrides list into Override objects."""
    overrides = []
    for i, o in enumerate(overrides_raw):
        overrides.append(
            Override(
                match=str(_require(o, "match", f"[[{context}.overrides]][{i}]")),
                freshness_column=o.get("freshness_column"),
                freshness_threshold_hours=o.get("freshness_threshold_hours"),
                volume_zscore_threshold=o.get("volume_zscore_threshold"),
                volume_method=o.get("volume_method"),
            )
        )
    return overrides


def _strip_none(d: dict) -> dict:
    """Recursively remove keys with ``None`` values from a dict."""
    result = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, dict):
            v = _strip_none(v)
        elif isinstance(v, list):
            v = [_strip_none(i) if isinstance(i, dict) else i for i in v]
        result[k] = v
    return result


def _connection_to_dict(conn: ConnectionConfig) -> dict:
    """Convert a ConnectionConfig to a TOML-friendly dict."""
    conn_dict: dict = {"type": conn.type}
    if conn.type == "duckdb":
        if conn.path is not None:
            conn_dict["path"] = conn.path
    elif conn.type == "postgres":
        if conn.url is not None:
            conn_dict["url"] = conn.url
    elif conn.type == "bigquery":
        if conn.project is not None:
            conn_dict["project"] = conn.project
        if conn.dataset is not None:
            conn_dict["dataset"] = conn.dataset
        if conn.region is not None:
            conn_dict["region"] = conn.region
        if not conn.use_information_schema_row_counts:
            conn_dict["use_information_schema_row_counts"] = False
    elif conn.type == "snowflake":
        if conn.account is not None:
            conn_dict["account"] = conn.account
        if conn.database is not None:
            conn_dict["database"] = conn.database
        if conn.use_account_usage:
            conn_dict["use_account_usage"] = True
    conn_dict.update(conn.extras)
    return conn_dict


def _config_to_dict(config: OllyConfig) -> dict:
    """Convert an ``OllyConfig`` to a TOML-friendly dict.

    Handles enum serialization, strips ``None`` values, and omits
    sections that are at their defaults (dbt, usage, cost, contracts).
    """
    connections_dict: dict = {}
    for name, nc in config.connections.items():
        conn_dict = _connection_to_dict(nc.connection)
        sel = asdict(nc.selection)
        ovr = [_strip_none(asdict(o)) for o in nc.overrides]
        conn_dict["selection"] = sel
        if ovr:
            conn_dict["overrides"] = ovr
        connections_dict[name] = conn_dict

    settings_dict = _strip_none(asdict(config.settings))
    data: dict = {
        "connections": connections_dict,
        "settings": settings_dict,
    }

    if config.integrity.module:
        data["integrity"] = {"module": config.integrity.module}
    if config.contracts.module:
        data["contracts"] = {"module": config.contracts.module}
    if config.dbt.run_results_path:
        dbt_data: dict = {"run_results_path": config.dbt.run_results_path}
        if config.dbt.include_skipped:
            dbt_data["include_skipped"] = config.dbt.include_skipped
        data["dbt"] = dbt_data
    if config.usage.enabled:
        data["usage"] = asdict(config.usage)
    if config.cost.enabled:
        data["cost"] = asdict(config.cost)
    if config.slack.webhook_url:
        data["slack"] = _strip_none(asdict(config.slack))

    return data


def write_config(config: OllyConfig, path: Path | None = None) -> None:
    """Serialize an ``OllyConfig`` to a TOML file.

    Args:
        config: The configuration to write.
        path: Destination file path. Defaults to ``olly.toml`` in the
            current directory.
    """
    if path is None:
        path = Path("olly.toml")

    data = _config_to_dict(config)

    with open(path, "wb") as f:
        tomli_w.dump(data, f)
