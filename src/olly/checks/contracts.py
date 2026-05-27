from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, cast

import ibis.expr.datatypes as dt

from olly.contracts import TableSpec
from olly.models import Finding

if TYPE_CHECKING:
    from olly.adapter import Adapter

logger = logging.getLogger(__name__)


def check_contracts(contracts: list[TableSpec], adapter: Adapter) -> list[Finding]:
    """Validate table schemas against declared contracts.

    Fetches the Ibis schema for each contracted table and compares its
    column types against the Python type annotations in the contract.

    Args:
        contracts: Expected table specifications to enforce.
        adapter: Warehouse adapter used to fetch table schemas.

    Returns:
        A list of findings for any contract violations found.
    """
    findings: list[Finding] = []
    logger.debug("Checking %d contracts", len(contracts))

    for contract in contracts:
        try:
            schema = adapter.fetch_table_schema(
                contract.schema_name, contract.table_name
            )
        except Exception:
            findings.append(
                Finding(
                    check_type="contracts",
                    severity="error",
                    schema_name=contract.schema_name,
                    table_name=contract.table_name,
                    description=(
                        f"Missing table: {contract.schema_name}.{contract.table_name}"
                    ),
                    details={"issue": "missing_table"},
                )
            )
            continue

        actual_cols = set(cast(list[str], schema.names))
        for col_name, expected in contract.columns.items():
            if col_name not in actual_cols:
                findings.append(
                    Finding(
                        check_type="contracts",
                        severity="error",
                        schema_name=contract.schema_name,
                        table_name=contract.table_name,
                        description=(
                            "Missing column: "
                            f"{contract.schema_name}.{contract.table_name}.{col_name}"
                        ),
                        details={"issue": "missing_column", "column": col_name},
                    )
                )
                continue

            ibis_type = schema[col_name]
            if not _type_compatible(expected.dtype, ibis_type):
                findings.append(
                    Finding(
                        check_type="contracts",
                        severity="error",
                        schema_name=contract.schema_name,
                        table_name=contract.table_name,
                        description=(
                            f"Column type mismatch: {col_name} expected "
                            f"{expected.dtype.__name__}, got {ibis_type}"
                        ),
                        details={
                            "issue": "type_mismatch",
                            "column": col_name,
                            "expected": expected.dtype.__name__,
                            "actual": str(ibis_type),
                        },
                    )
                )

            if expected.nullable != ibis_type.nullable:
                findings.append(
                    Finding(
                        check_type="contracts",
                        severity="error",
                        schema_name=contract.schema_name,
                        table_name=contract.table_name,
                        description=(
                            f"Column nullability mismatch: {col_name} expected "
                            f"nullable={expected.nullable}, got nullable={ibis_type.nullable}"
                        ),
                        details={
                            "issue": "nullability_mismatch",
                            "column": col_name,
                            "expected": expected.nullable,
                            "actual": ibis_type.nullable,
                        },
                    )
                )

        if contract.strict:
            for col_name in actual_cols:
                if col_name not in contract.columns:
                    findings.append(
                        Finding(
                            check_type="contracts",
                            severity="error",
                            schema_name=contract.schema_name,
                            table_name=contract.table_name,
                            description=(
                                "Unexpected column: "
                                f"{contract.schema_name}.{contract.table_name}.{col_name}"
                            ),
                            details={"issue": "extra_column", "column": col_name},
                        )
                    )

    return findings


def _type_compatible(expected: type, ibis_type: dt.DataType) -> bool:
    """Check if an Ibis data type is compatible with the expected Python type."""
    if expected is int:
        return isinstance(ibis_type, dt.Integer)

    if expected is float:
        return isinstance(ibis_type, (dt.Floating, dt.Decimal))

    if expected is Decimal:
        return isinstance(ibis_type, dt.Decimal)

    if expected is str:
        return isinstance(ibis_type, dt.String)

    if expected is bool:
        return isinstance(ibis_type, dt.Boolean)

    if expected is datetime:
        return isinstance(ibis_type, dt.Timestamp)

    if expected is date:
        return isinstance(ibis_type, dt.Date)

    return False
