from __future__ import annotations

import logging

from olly.models import Finding, TableInfo

logger = logging.getLogger(__name__)


def check_schema(
    current: list[TableInfo],
    baseline: list[TableInfo],
) -> list[Finding]:
    """Compare current and baseline schemas to detect structural changes.

    Detects added/removed tables, materialization changes, and column-level
    diffs (added, removed, type changed, nullability changed).

    Args:
        current: Table schemas from the latest warehouse snapshot.
        baseline: Table schemas from the previous snapshot.

    Returns:
        A list of findings describing each detected schema change.
    """
    findings: list[Finding] = []
    logger.debug(
        "Comparing %d current vs %d baseline tables", len(current), len(baseline)
    )

    current_map = {(t.schema_name, t.table_name): t for t in current}
    baseline_map = {(t.schema_name, t.table_name): t for t in baseline}

    current_keys = set(current_map)
    baseline_keys = set(baseline_map)

    # New tables
    for key in sorted(current_keys - baseline_keys):
        t = current_map[key]
        findings.append(
            Finding(
                check_type="schema",
                severity="warning",
                schema_name=t.schema_name,
                table_name=t.table_name,
                description=f"New table detected: {t.schema_name}.{t.table_name}",
                details={"change": "table_added", "table_type": t.table_type},
            )
        )

    # Removed tables
    for key in sorted(baseline_keys - current_keys):
        t = baseline_map[key]
        findings.append(
            Finding(
                check_type="schema",
                severity="error",
                schema_name=t.schema_name,
                table_name=t.table_name,
                description=f"Table removed: {t.schema_name}.{t.table_name}",
                details={"change": "table_removed", "table_type": t.table_type},
            )
        )

    # Compare tables that exist in both
    for key in sorted(current_keys & baseline_keys):
        cur = current_map[key]
        base = baseline_map[key]

        # Materialization change
        if cur.table_type != base.table_type:
            findings.append(
                Finding(
                    check_type="schema",
                    severity="warning",
                    schema_name=cur.schema_name,
                    table_name=cur.table_name,
                    description=(
                        f"Materialization changed: {cur.schema_name}.{cur.table_name} "
                        f"({base.table_type} -> {cur.table_type})"
                    ),
                    details={
                        "change": "materialization_changed",
                        "old_type": base.table_type,
                        "new_type": cur.table_type,
                    },
                )
            )

        # Column-level diffs
        cur_cols = {c.column_name: c for c in cur.columns}
        base_cols = {c.column_name: c for c in base.columns}

        for col_name in sorted(set(cur_cols) - set(base_cols)):
            c = cur_cols[col_name]
            findings.append(
                Finding(
                    check_type="schema",
                    severity="warning",
                    schema_name=cur.schema_name,
                    table_name=cur.table_name,
                    description=f"New column: {cur.schema_name}.{cur.table_name}.{col_name}",
                    details={
                        "change": "column_added",
                        "column": col_name,
                        "data_type": c.data_type,
                        "is_nullable": c.is_nullable,
                    },
                )
            )

        for col_name in sorted(set(base_cols) - set(cur_cols)):
            findings.append(
                Finding(
                    check_type="schema",
                    severity="error",
                    schema_name=cur.schema_name,
                    table_name=cur.table_name,
                    description=f"Column removed: {cur.schema_name}.{cur.table_name}.{col_name}",
                    details={"change": "column_removed", "column": col_name},
                )
            )

        for col_name in sorted(set(cur_cols) & set(base_cols)):
            cc = cur_cols[col_name]
            bc = base_cols[col_name]

            if cc.data_type != bc.data_type:
                findings.append(
                    Finding(
                        check_type="schema",
                        severity="error",
                        schema_name=cur.schema_name,
                        table_name=cur.table_name,
                        description=(
                            f"Type changed: {cur.schema_name}.{cur.table_name}.{col_name} "
                            f"({bc.data_type} -> {cc.data_type})"
                        ),
                        details={
                            "change": "type_changed",
                            "column": col_name,
                            "old_type": bc.data_type,
                            "new_type": cc.data_type,
                        },
                    )
                )

            if cc.is_nullable != bc.is_nullable:
                findings.append(
                    Finding(
                        check_type="schema",
                        severity="warning",
                        schema_name=cur.schema_name,
                        table_name=cur.table_name,
                        description=(
                            f"Nullability changed: {cur.schema_name}.{cur.table_name}.{col_name} "
                            f"(nullable={bc.is_nullable} -> nullable={cc.is_nullable})"
                        ),
                        details={
                            "change": "nullability_changed",
                            "column": col_name,
                            "old_nullable": bc.is_nullable,
                            "new_nullable": cc.is_nullable,
                        },
                    )
                )

    return findings
