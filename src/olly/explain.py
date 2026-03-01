from __future__ import annotations

import logging
from dataclasses import dataclass

from olly.adapter import Adapter
from olly.config import NamedConnection, OllyConfig, ResolvedTableSettings
from olly.config_ops import (
    filter_table_infos,
    match_pattern,
    resolve_connections,
    resolve_table_settings_with_sources,
    select_schema_names,
    validate_config,
)

logger = logging.getLogger(__name__)

@dataclass
class SchemaMatch:
    """Result of matching a single schema against include/exclude filters.

    Attributes:
        name: Schema name.
        included: Whether the schema was selected.
        reason: Why the schema was excluded (``None`` when included).
    """

    name: str
    included: bool
    reason: str | None = None


@dataclass
class ConnectionExplain:
    """Explain result for a single connection."""

    name: str
    nc: NamedConnection
    schema_matches: list[SchemaMatch]
    table_matches: list[str]
    table_settings: dict[str, ResolvedTableSettings]


@dataclass
class ExplainResult:
    """Full output of the config-explain analysis.

    Attributes:
        config: The parsed Olly configuration.
        connection_explains: Per-connection explain results.
        warnings: Config validation warnings.
    """

    config: OllyConfig
    connection_explains: list[ConnectionExplain]
    warnings: list[str]


def explain_config(
    config: OllyConfig,
    backends: dict[str, Adapter],
    connection_name: str | None = None,
) -> ExplainResult:
    """Analyze the current config against live backends.

    Args:
        config: Parsed ``OllyConfig``.
        backends: Dict mapping connection name to adapter instance. Connections
            missing from the dict are shown with config-only output.
        connection_name: Optional connection name to explain.

    Returns:
        An ``ExplainResult`` with matched schemas, tables, settings, and
        any config warnings.
    """
    connection_explains: list[ConnectionExplain] = []
    connections = resolve_connections(config, connection_name)
    logger.info("Explaining %d connection(s)", len(connections))

    for name, nc in connections:
        backend = backends.get(name)
        if backend is None:
            logger.warning("Connection '%s': no backend available, showing config only", name)
            available_schemas: list[str] = []
        else:
            logger.info("Connection '%s': connected successfully", name)
            try:
                available_schemas = backend.list_schemas()
                logger.info("Connection '%s': found %d schemas", name, len(available_schemas))
            except Exception:
                logger.warning("Connection '%s': list_schemas failed, falling back to config only", name)
                available_schemas = []
        exclude_schemas = nc.selection.exclude_schemas
        selected_schemas = select_schema_names(nc.selection, available_schemas)
        selected_set = set(selected_schemas)
        logger.info("Connection '%s': selected %d of %d schemas", name, len(selected_schemas), len(available_schemas))

        schema_matches: list[SchemaMatch] = []
        for schema in available_schemas:
            if schema in selected_set:
                schema_matches.append(SchemaMatch(name=schema, included=True))
            else:
                excluded = any(match_pattern(pat, schema) for pat in exclude_schemas)
                reason = "excluded" if excluded else "not included"
                schema_matches.append(
                    SchemaMatch(name=schema, included=False, reason=reason)
                )
        if backend is not None and selected_schemas:
            logger.info("Connection '%s': fetching schema info for %s", name, selected_schemas)
            tables = backend.fetch_schema_info(selected_schemas)
            tables = filter_table_infos(nc.selection, tables)
            logger.info("Connection '%s': found %d tables after filtering", name, len(tables))
        else:
            tables = []

        table_matches = [f"{t.schema_name}.{t.table_name}" for t in tables]
        table_settings = {
            f"{t.schema_name}.{t.table_name}": resolve_table_settings_with_sources(
                config.settings, nc.overrides, t.schema_name, t.table_name
            )
            for t in tables
        }

        connection_explains.append(
            ConnectionExplain(
                name=name,
                nc=nc,
                schema_matches=schema_matches,
                table_matches=sorted(table_matches),
                table_settings=table_settings,
            )
        )

    warnings = validate_config(config)

    return ExplainResult(
        config=config,
        connection_explains=connection_explains,
        warnings=warnings,
    )


def format_explain(result: ExplainResult) -> str:
    """Format an ``ExplainResult`` as a human-readable multiline string.

    Args:
        result: The explain result to format.

    Returns:
        Plain-text report showing selection rules, matched schemas/tables,
        resolved overrides, and any warnings.
    """
    lines: list[str] = []
    lines.append("Config explain (olly.toml)")
    lines.append("")

    for ce in result.connection_explains:
        if len(result.connection_explains) > 1:
            lines.append(f"Connection: {ce.name}")
            lines.append("")

        selection = ce.nc.selection
        lines.append("Selection")
        lines.append(f"  include_schemas: {selection.include_schemas}")
        lines.append(f"  exclude_schemas: {selection.exclude_schemas}")
        lines.append(f"  include_tables: {selection.include_tables}")
        lines.append(f"  exclude_tables: {selection.exclude_tables}")

        lines.append("")
        lines.append("Matched schemas")
        for match in ce.schema_matches:
            if match.included:
                lines.append(f"  + {match.name}")
            elif match.reason:
                lines.append(f"  - {match.name} ({match.reason})")

        lines.append("")
        lines.append("Matched tables")
        if ce.table_matches:
            for table in ce.table_matches:
                lines.append(f"  + {table}")
        else:
            lines.append("  <none>")

        lines.append("")
        lines.append("Overrides (precedence: global -> schema -> pattern -> object)")
        if ce.table_settings:
            for table in sorted(ce.table_settings.keys()):
                settings = ce.table_settings[table]
                lines.append(f"  {table}")
                freshness_column = settings.freshness_column or "<none>"
                lines.append(
                    "    "
                    f"freshness_column: {freshness_column} "
                    f"({settings.freshness_column_source})"
                )
                lines.append(
                    "    "
                    f"freshness_threshold_hours: {settings.freshness_threshold_hours} "
                    f"({settings.freshness_threshold_hours_source})"
                )
                lines.append(
                    "    "
                    f"volume_zscore_threshold: {settings.volume_zscore_threshold} "
                    f"({settings.volume_zscore_threshold_source})"
                )
                lines.append(
                    "    "
                    f"volume_method: {settings.volume_method} "
                    f"({settings.volume_method_source})"
                )
        else:
            lines.append("  <none>")

        lines.append("")

    if result.warnings:
        lines.append("Warnings")
        for warning in result.warnings:
            lines.append(f"  - {warning}")

    return "\n".join(lines)
