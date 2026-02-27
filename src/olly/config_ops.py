from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from olly.config import (
    NamedConnection,
    Override,
    ResolvedTableSettings,
    Selection,
    Settings,
)

if TYPE_CHECKING:
    from olly.config import OllyConfig
    from olly.models import TableInfo

logger = logging.getLogger(__name__)


def match_pattern(pattern: str, value: str) -> bool:
    """Test whether a glob-style pattern matches a value.

    Supports ``*`` as a wildcard for any sequence of characters.

    Args:
        pattern: Glob pattern (e.g. ``"*"`` or ``"stg_*"``).
        value: String to match against.

    Returns:
        ``True`` if the pattern matches the entire value.
    """
    if pattern == "*":
        return True
    regex = "^" + re.escape(pattern).replace("\\*", ".*") + "$"
    return re.match(regex, value, re.IGNORECASE) is not None


def match_table_pattern(pattern: str, schema: str, table: str) -> bool:
    """Test whether a ``schema.table`` glob pattern matches a given table.

    Args:
        pattern: A dot-separated pattern like ``"main.*"`` or ``"*.orders"``.
        schema: Schema name to match.
        table: Table name to match.

    Returns:
        ``True`` if both the schema and table portions match.
    """
    if "." not in pattern:
        return False
    schema_pattern, table_pattern = pattern.split(".", 1)
    return match_pattern(schema_pattern, schema) and match_pattern(table_pattern, table)


def select_schema_names(
    selection: Selection, available_schemas: list[str]
) -> list[str]:
    """Filter available schema names using the configured include/exclude rules.

    Args:
        selection: Selection filters.
        available_schemas: Schema names reported by the warehouse.

    Returns:
        Subset of *available_schemas* that pass the inclusion/exclusion filters.
    """
    include_schemas = selection.include_schemas or ["*"]
    exclude_schemas = selection.exclude_schemas

    selected = []
    for schema in available_schemas:
        included = any(match_pattern(pat, schema) for pat in include_schemas)
        excluded = any(match_pattern(pat, schema) for pat in exclude_schemas)
        if included and not excluded:
            selected.append(schema)
    return selected


def filter_table_infos(
    selection: Selection, tables: list[TableInfo]
) -> list[TableInfo]:
    """Filter table info objects using the configured include/exclude table patterns.

    Args:
        selection: Selection filters.
        tables: Table info objects to filter.

    Returns:
        Subset of *tables* that pass the inclusion/exclusion filters.
    """
    include_tables = selection.include_tables or ["*.*"]
    exclude_tables = selection.exclude_tables

    filtered = []
    for ti in tables:
        included = any(
            match_table_pattern(pat, ti.schema_name, ti.table_name)
            for pat in include_tables
        )
        excluded = any(
            match_table_pattern(pat, ti.schema_name, ti.table_name)
            for pat in exclude_tables
        )
        if included and not excluded:
            filtered.append(ti)
    return filtered


def resolve_table_settings_with_sources(
    settings: Settings,
    overrides: list[Override],
    schema: str,
    table: str,
) -> ResolvedTableSettings:
    """Resolve effective settings for a specific table, tracking provenance.

    Applies overrides in precedence order -- schema-level, then pattern-level
    (wildcards), then object-level (exact ``schema.table``) -- so that more
    specific overrides win.

    Args:
        config: Olly configuration with global settings and overrides.
        schema: Schema name of the table.
        table: Table name.

    Returns:
        ``ResolvedTableSettings`` containing the final value and originating
        source (``"global"``, ``"schema"``, ``"pattern"``, or ``"object"``)
        for each setting.
    """
    freshness_column: str | None = None
    freshness_threshold_hours = settings.freshness_threshold_hours
    volume_zscore_threshold = settings.volume_zscore_threshold
    sources = {
        "freshness_column": "global",
        "freshness_threshold_hours": "global",
        "volume_zscore_threshold": "global",
    }

    def apply_override(override: Override, source: str) -> None:
        """Apply non-None fields from *override*, tagging each with *source*."""
        nonlocal freshness_column, freshness_threshold_hours, volume_zscore_threshold
        if override.freshness_column is not None:
            freshness_column = override.freshness_column
            sources["freshness_column"] = source
        if override.freshness_threshold_hours is not None:
            freshness_threshold_hours = override.freshness_threshold_hours
            sources["freshness_threshold_hours"] = source
        if override.volume_zscore_threshold is not None:
            volume_zscore_threshold = override.volume_zscore_threshold
            sources["volume_zscore_threshold"] = source

    # Schema-level overrides (exact schema)
    for override in overrides:
        if "*" in override.match or "." in override.match:
            continue
        if override.match == schema:
            apply_override(override, "schema")

    # Pattern-level overrides (wildcards)
    for override in overrides:
        if "*" not in override.match:
            continue
        if "." in override.match:
            if match_table_pattern(override.match, schema, table):
                apply_override(override, "pattern")
        else:
            if match_pattern(override.match, schema):
                apply_override(override, "pattern")

    # Object-level overrides (exact schema.table)
    for override in overrides:
        if "*" in override.match or "." not in override.match:
            continue
        if override.match == f"{schema}.{table}":
            apply_override(override, "object")

    return ResolvedTableSettings(
        freshness_column=freshness_column,
        freshness_threshold_hours=freshness_threshold_hours,
        volume_zscore_threshold=volume_zscore_threshold,
        freshness_column_source=sources["freshness_column"],
        freshness_threshold_hours_source=sources["freshness_threshold_hours"],
        volume_zscore_threshold_source=sources["volume_zscore_threshold"],
    )


def validate_config(config: OllyConfig) -> list[str]:
    """Check a configuration for common mistakes and return warnings.

    Args:
        config: The configuration to validate.

    Returns:
        List of human-readable warning strings. An empty list means the
        configuration looks correct.
    """
    warnings: list[str] = []
    logger.debug("Validating config")

    for conn_name, nc in config.connections.items():
        prefix = f"connections.{conn_name}" if len(config.connections) > 1 else ""

        if not nc.selection.include_schemas:
            label = f"{prefix}.selection" if prefix else "selection"
            warnings.append(f"{label}.include_schemas is empty; no schemas will match.")

        for pat in nc.selection.include_tables + nc.selection.exclude_tables:
            if "." not in pat:
                warnings.append(
                    f"Table pattern '{pat}' is missing a schema prefix (expected schema.table)."
                )

        for override in nc.overrides:
            if not override.match:
                warnings.append("Override has an empty match pattern.")
                continue
            if override.match.count(".") > 1:
                warnings.append(
                    f"Override match '{override.match}' contains multiple dots;"
                    " only schema or schema.table is supported."
                )
            if (
                override.freshness_column is None
                and override.freshness_threshold_hours is None
                and override.volume_zscore_threshold is None
            ):
                warnings.append(f"Override '{override.match}' has no fields set.")

    if config.integrity.module is not None and not config.integrity.module.strip():
        warnings.append("integrity.module is set but empty.")

    if config.usage.enabled:
        if config.usage.lookback_days < config.usage.unused_threshold_days:
            warnings.append(
                "usage.lookback_days must be >= usage.unused_threshold_days."
            )

    if config.contracts.module is not None and not config.contracts.module.strip():
        warnings.append("contracts.module is set but empty.")

    if config.dbt.run_results_path is not None:
        dbt_path = Path(config.dbt.run_results_path)
        if not dbt_path.is_absolute() and config.config_path is not None:
            dbt_path = config.config_path.parent / dbt_path
        if not dbt_path.exists():
            warnings.append(
                f"dbt.run_results_path '{config.dbt.run_results_path}' does not exist."
            )

    return warnings


def resolve_connections(
    config: OllyConfig, name: str | None
) -> list[tuple[str, NamedConnection]]:
    """Return the connections to operate on, filtered by name if given.

    Args:
        config: Olly configuration with connections dict.
        name: Optional connection name to select. When None, all connections
            are returned.

    Returns:
        List of (connection_name, NamedConnection) tuples.

    Raises:
        ValueError: If *name* does not match any configured connection.
    """
    if name is not None:
        if name not in config.connections:
            available = ", ".join(sorted(config.connections))
            raise ValueError(
                f"Unknown connection '{name}'. Available: {available}"
            )
        nc = config.connections[name]
        return [(name, nc)]
    return list(config.connections.items())
