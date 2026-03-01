from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from olly._import import import_module_spec
from olly.adapter import connect_typed
from olly.config import NamedConnection
from olly.models import Finding, IntegrityMethod, Sync, WindowOp

logger = logging.getLogger(__name__)


def load_syncs(module_spec: str, config_path: Path | None = None) -> list[Sync]:
    """Import a module and return its ``syncs`` list.

    Args:
        module_spec: Dotted module path or file path to a Python file
            containing a module-level ``syncs`` variable.
        config_path: Path to ``olly.toml``, used to resolve relative file
            paths. Defaults to the current working directory.

    Returns:
        List of ``Sync`` instances from the module.

    Raises:
        ValueError: If *module_spec* is blank, the module has no ``syncs``
            attribute, or the list is empty.
    """
    if not module_spec or not module_spec.strip():
        raise ValueError("integrity.module must be set to a module path or file path.")
    module = import_module_spec(module_spec, config_path, label="integrity")
    syncs = getattr(module, "syncs", None)
    if syncs is None:
        raise ValueError(f"No 'syncs' attribute found in {module_spec}")
    if not syncs:
        raise ValueError(f"'syncs' list is empty in {module_spec}")
    return list(syncs)


def run_syncs(
    syncs: list[Sync],
    *,
    connections: dict[str, NamedConnection],
) -> list[Finding]:
    """Run cross-source integrity checks for configured syncs.

    Compares source and target data using the method specified on each sync
    (count, count_distinct, pk, or hash) within a resolved time window.

    Args:
        syncs: Sync definitions to evaluate.
        connections: Mapping of connection names to NamedConnection objects.

    Returns:
        A list of findings for syncs where source/target data diverges.

    Raises:
        ValueError: If connections are missing, syncs lack required fields,
            or an unsupported method is specified.
    """
    if not syncs:
        return []
    logger.debug("Running %d integrity syncs", len(syncs))
    if not connections:
        raise ValueError("Integrity checks require connections to be provided.")

    findings: list[Finding] = []
    for pipeline in syncs:
        source_nc = connections.get(pipeline.source)
        target_nc = connections.get(pipeline.target)
        if not source_nc or not target_nc:
            raise ValueError(
                f"Integrity pipeline '{pipeline.name}' references unknown connections."
            )
        if pipeline.window is None:
            raise ValueError(
                f"Integrity pipeline '{pipeline.name}' is missing a window specification."
            )
        if pipeline.watermark is None:
            raise ValueError(
                f"Integrity pipeline '{pipeline.name}' is missing a watermark column."
            )
        if (
            pipeline.method
            in {
                IntegrityMethod.PK,
                IntegrityMethod.COUNT_DISTINCT,
                IntegrityMethod.HASH,
            }
            and not pipeline.key
        ):
            raise ValueError(
                f"Integrity pipeline '{pipeline.name}' requires a key for method "
                f"'{pipeline.method.value}'."
            )

        source_backend = connect_typed(source_nc.connection)
        target_backend = connect_typed(target_nc.connection)
        source_schema, source_table = _parse_table_ref(pipeline.source_table)
        target_schema, target_table = _parse_table_ref(pipeline.target_table)

        window_start, window_end = _resolve_window(pipeline)
        window_start, window_end = _apply_tolerance_window_end(
            pipeline,
            target_backend,
            target_schema,
            target_table,
            window_start,
            window_end,
        )

        where_sql = _build_where_sql(
            pipeline.watermark, window_start, window_end, pipeline.where
        )

        if pipeline.method in {
            IntegrityMethod.COUNT,
            IntegrityMethod.COUNT_DISTINCT,
            IntegrityMethod.PK,
        }:
            finding = _run_numeric_check(
                pipeline,
                source_backend,
                target_backend,
                source_schema,
                source_table,
                target_schema,
                target_table,
                where_sql,
                window_start,
                window_end,
            )
            if finding:
                findings.append(finding)
            continue

        if pipeline.method == IntegrityMethod.HASH:
            assert pipeline.key is not None  # validated upfront
            if pipeline.hash_columns is None:
                hash_columns = [pipeline.key]
            else:
                hash_columns = [str(col) for col in pipeline.hash_columns]
            if not hash_columns:
                raise ValueError(
                    f"Integrity pipeline '{pipeline.name}' requires hash_columns."
                )
            source_hash = source_backend.fetch_hash(
                source_schema,
                source_table,
                hash_columns,
                pipeline.key,
                where_sql,
            )
            target_hash = target_backend.fetch_hash(
                target_schema,
                target_table,
                hash_columns,
                pipeline.key,
                where_sql,
            )
            if source_hash != target_hash:
                findings.append(
                    Finding(
                        check_type="integrity",
                        severity=pipeline.severity,
                        schema_name=target_schema,
                        table_name=target_table,
                        description=(
                            f"Integrity check failed for {pipeline.name} "
                            "(hash mismatch)."
                        ),
                        details={
                            "pipeline": pipeline.name,
                            "method": pipeline.method.value,
                            "source": pipeline.source,
                            "target": pipeline.target,
                            "source_table": pipeline.source_table,
                            "target_table": pipeline.target_table,
                            "source_hash": source_hash,
                            "target_hash": target_hash,
                            "hash_columns": hash_columns,
                            "window_start": _format_timestamp(window_start),
                            "window_end": _format_timestamp(window_end),
                            "where": pipeline.where,
                        },
                    )
                )
            continue

        raise ValueError(f"Unsupported integrity method: {pipeline.method}")

    return findings


def _compare_numeric(
    pipeline: Sync,
    target_schema: str,
    target_table: str,
    source_value: int,
    target_value: int,
    window_start: datetime,
    window_end: datetime,
) -> Finding | None:
    """Compare numeric source and target values, applying tolerance if configured.

    Returns a finding when the values diverge beyond the configured
    ``tolerance_delta`` and/or ``tolerance_ratio``, or are not equal when no
    tolerance is set.
    """
    diff = source_value - target_value
    if source_value == 0:
        ratio = 1.0 if target_value == 0 else 0.0
    else:
        ratio = target_value / source_value

    if pipeline.tolerance_delta is None and pipeline.tolerance_ratio is None:
        passed = diff == 0
    else:
        passed = False
        if pipeline.tolerance_delta is not None:
            passed = passed or abs(diff) <= pipeline.tolerance_delta
        if pipeline.tolerance_ratio is not None:
            passed = passed or ratio >= pipeline.tolerance_ratio

    if passed:
        return None

    details = {
        "pipeline": pipeline.name,
        "method": pipeline.method.value,
        "source": pipeline.source,
        "target": pipeline.target,
        "source_table": pipeline.source_table,
        "target_table": pipeline.target_table,
        "source_value": source_value,
        "target_value": target_value,
        "diff": diff,
        "ratio": ratio,
        "window_start": _format_timestamp(window_start),
        "window_end": _format_timestamp(window_end),
        "where": pipeline.where,
        "tolerance_delta": pipeline.tolerance_delta,
        "tolerance_ratio": pipeline.tolerance_ratio,
        "tolerance_mode": pipeline.tolerance_mode,
    }

    return Finding(
        check_type="integrity",
        severity=pipeline.severity,
        schema_name=target_schema,
        table_name=target_table,
        description=(
            f"Integrity check failed for {pipeline.name} ({pipeline.method.value})."
        ),
        details=details,
    )


def _run_numeric_check(
    pipeline: Sync,
    source_backend,
    target_backend,
    source_schema: str,
    source_table: str,
    target_schema: str,
    target_table: str,
    where_sql: str,
    window_start: datetime,
    window_end: datetime,
) -> Finding | None:
    """Fetch numeric values from source/target and compare them.

    Uses ``fetch_count`` for COUNT pipelines and ``fetch_count_distinct``
    for COUNT_DISTINCT and PK pipelines.
    """
    if pipeline.method == IntegrityMethod.COUNT:
        source_value = source_backend.fetch_count(
            source_schema, source_table, where_sql
        )
        target_value = target_backend.fetch_count(
            target_schema, target_table, where_sql
        )
    else:
        assert pipeline.key is not None  # validated upfront
        source_value = source_backend.fetch_count_distinct(
            source_schema, source_table, pipeline.key, where_sql
        )
        target_value = target_backend.fetch_count_distinct(
            target_schema, target_table, pipeline.key, where_sql
        )
    return _compare_numeric(
        pipeline,
        target_schema,
        target_table,
        source_value,
        target_value,
        window_start,
        window_end,
    )


def _resolve_window(pipeline: Sync) -> tuple[datetime, datetime]:
    """Resolve a pipeline's window specification into a start/end datetime pair.

    Raises:
        ValueError: If the window is missing or has an unsupported operation.
    """
    if pipeline.window is None:
        raise ValueError(f"Integrity pipeline '{pipeline.name}' is missing a window.")
    op = pipeline.window.op
    if op == WindowOp.GT_NOW:
        if not pipeline.window.duration:
            raise ValueError(
                f"Integrity pipeline '{pipeline.name}' requires duration for gt_now."
            )
        now = datetime.now(timezone.utc)
        delta = _parse_duration(pipeline.window.duration)
        return now - delta, now
    if op == WindowOp.BETWEEN:
        if not pipeline.window.start or not pipeline.window.end:
            raise ValueError(
                f"Integrity pipeline '{pipeline.name}' requires start/end for between."
            )
        return _parse_timestamp(pipeline.window.start), _parse_timestamp(
            pipeline.window.end
        )
    if op == WindowOp.EQ_TS:
        if not pipeline.window.value:
            raise ValueError(
                f"Integrity pipeline '{pipeline.name}' requires value for eq_ts."
            )
        value = _parse_timestamp(pipeline.window.value)
        return value, value
    if op == WindowOp.EQ_DATE:
        if not pipeline.window.value:
            raise ValueError(
                f"Integrity pipeline '{pipeline.name}' requires value for eq_date."
            )
        day = date.fromisoformat(pipeline.window.value)
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1) - timedelta(microseconds=1)
        return start, end

    raise ValueError(f"Unsupported window op: {op}")


def _apply_tolerance_window_end(
    pipeline: Sync,
    target_backend,
    target_schema: str,
    target_table: str,
    window_start: datetime,
    window_end: datetime,
) -> tuple[datetime, datetime]:
    """Clamp the window end to the target's max watermark when tolerance mode requires it."""
    if pipeline.tolerance_mode != "target_max_watermark":
        return window_start, window_end

    target_max = target_backend.fetch_max_timestamp(
        target_schema, target_table, pipeline.watermark
    )
    if target_max is None:
        return window_start, window_end

    if target_max < window_end:
        window_end = target_max
    if window_end < window_start:
        window_end = window_start
    return window_start, window_end


def _build_where_sql(
    watermark: str, window_start: datetime, window_end: datetime, where: str | None
) -> str:
    """Build a SQL WHERE clause filtering the watermark column to the given window."""
    base = (
        f"{watermark} >= '{_format_timestamp(window_start)}' AND "
        f"{watermark} <= '{_format_timestamp(window_end)}'"
    )
    if where:
        return f"({base}) AND ({where})"
    return base


def _parse_table_ref(value: str) -> tuple[str, str]:
    """Parse a ``schema.table`` reference into its component parts."""
    if "." not in value:
        raise ValueError(f"Expected table reference in form schema.table: {value}")
    schema_name, table_name = value.split(".", 1)
    return schema_name, table_name


def _parse_duration(value: str) -> timedelta:
    """Parse a compact duration string (e.g., ``30m``, ``2h``, ``7d``) into a timedelta."""
    match = re.match(r"^(\d+)([smhd])$", value)
    if not match:
        raise ValueError(f"Invalid duration: {value}")
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    raise ValueError(f"Unsupported duration unit: {unit}")


def _parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp string into a naive datetime."""
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1]
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def _format_timestamp(value: datetime) -> str:
    """Format a datetime as a SQL-friendly timestamp string."""
    if value.microsecond:
        return value.strftime("%Y-%m-%d %H:%M:%S.%f")
    return value.strftime("%Y-%m-%d %H:%M:%S")
