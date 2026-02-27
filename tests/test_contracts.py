from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import ibis
import ibis.expr.datatypes as dt
import pytest

from olly.checks.contracts import _type_compatible, check_contracts
from olly.contracts import ColumnContract, TableSpec, load_contracts
from conftest import FakeAdapter


def _schema(cols: Any) -> ibis.Schema:
    """Create an ibis.Schema from a dict (wraps for type checker)."""
    return ibis.Schema(cols)


def test_contracts_missing_table():
    contracts = [
        TableSpec(
            schema_name="main",
            table_name="orders",
            strict=False,
            columns={"id": ColumnContract(int, nullable=False)},
        )
    ]
    adapter = FakeAdapter()
    findings = check_contracts(contracts, cast(Any, adapter))
    assert len(findings) == 1
    assert findings[0].details["issue"] == "missing_table"


def test_contracts_missing_column():
    contracts = [
        TableSpec(
            schema_name="main",
            table_name="orders",
            strict=False,
            columns={
                "id": ColumnContract(int, nullable=False),
                "missing_col": ColumnContract(str),
            },
        )
    ]
    schema = _schema({"id": dt.Int32(nullable=False)})
    adapter = FakeAdapter({("main", "orders"): schema})
    findings = check_contracts(contracts, cast(Any, adapter))
    assert len(findings) == 1
    assert findings[0].details["issue"] == "missing_column"
    assert findings[0].details["column"] == "missing_col"


def test_contracts_type_mismatch():
    contracts = [
        TableSpec(
            schema_name="main",
            table_name="orders",
            strict=False,
            columns={"id": ColumnContract(int, nullable=False)},
        )
    ]
    # actual type is float64 — should mismatch int
    schema = _schema({"id": dt.Float64(nullable=False)})
    adapter = FakeAdapter({("main", "orders"): schema})
    findings = check_contracts(contracts, cast(Any, adapter))
    type_findings = [f for f in findings if f.details.get("issue") == "type_mismatch"]
    assert len(type_findings) == 1
    assert type_findings[0].details["column"] == "id"


def test_contracts_type_match_int_variants():
    """int annotation should match int8, int16, int32, int64."""
    for ibis_type in (dt.Int8, dt.Int16, dt.Int32, dt.Int64):
        contracts = [
            TableSpec(
                schema_name="main",
                table_name="t",
                strict=False,
                columns={"x": ColumnContract(int, nullable=False)},
            )
        ]
        schema = _schema({"x": ibis_type(nullable=False)})
        adapter = FakeAdapter({("main", "t"): schema})
        findings = check_contracts(contracts, cast(Any, adapter))
        type_findings = [
            f for f in findings if f.details.get("issue") == "type_mismatch"
        ]
        assert len(type_findings) == 0, f"int should match {ibis_type}"


def test_contracts_type_match_datetime():
    """datetime annotation should match Timestamp."""
    contracts = [
        TableSpec(
            schema_name="main",
            table_name="t",
            strict=False,
            columns={"ts": ColumnContract(datetime, nullable=False)},
        )
    ]
    schema = _schema({"ts": dt.Timestamp(nullable=False)})
    adapter = FakeAdapter({("main", "t"): schema})
    findings = check_contracts(contracts, cast(Any, adapter))
    type_findings = [f for f in findings if f.details.get("issue") == "type_mismatch"]
    assert len(type_findings) == 0


def test_contracts_nullability_mismatch():
    contracts = [
        TableSpec(
            schema_name="main",
            table_name="orders",
            strict=False,
            columns={"id": ColumnContract(int, nullable=False)},
        )
    ]
    # Nullable Int32 — expected not nullable
    schema = _schema({"id": dt.Int32(nullable=True)})
    adapter = FakeAdapter({("main", "orders"): schema})
    findings = check_contracts(contracts, cast(Any, adapter))
    null_findings = [
        f for f in findings if f.details.get("issue") == "nullability_mismatch"
    ]
    assert len(null_findings) == 1


def test_contracts_strict_extra_column():
    contracts = [
        TableSpec(
            schema_name="main",
            table_name="orders",
            strict=True,
            columns={"id": ColumnContract(int, nullable=False)},
        )
    ]
    schema = _schema(
        {
            "id": dt.Int64(nullable=False),
            "extra": dt.String(nullable=True),
        }
    )
    adapter = FakeAdapter({("main", "orders"): schema})
    findings = check_contracts(contracts, cast(Any, adapter))
    extra_findings = [f for f in findings if f.details.get("issue") == "extra_column"]
    assert len(extra_findings) == 1
    assert extra_findings[0].details["column"] == "extra"


def test_contracts_all_pass():
    """No findings when contract matches the actual schema."""
    contracts = [
        TableSpec(
            schema_name="main",
            table_name="orders",
            strict=False,
            columns={
                "id": ColumnContract(int, nullable=False),
                "amount": ColumnContract(float, nullable=False),
                "name": ColumnContract(str, nullable=False),
            },
        )
    ]
    schema = _schema(
        {
            "id": dt.Int32(nullable=False),
            "amount": dt.Float64(nullable=False),
            "name": dt.String(nullable=False),
        }
    )
    adapter = FakeAdapter({("main", "orders"): schema})
    findings = check_contracts(contracts, cast(Any, adapter))
    assert len(findings) == 0


def test_load_contracts_from_file_path(tmp_path):
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    contracts_file = contracts_dir / "contracts.py"
    contracts_file.write_text(
        "\n".join(
            [
                "from datetime import datetime",
                "from olly.contracts import TableContract",
                "",
                "class Orders(TableContract):",
                "    __schema__ = 'main'",
                "    __table__ = 'orders'",
                "",
                "    id: int",
                "    created_at: datetime",
                "",
            ]
        )
    )
    config_path = tmp_path / "olly.toml"
    config_path.write_text("")

    specs = load_contracts(str(Path("contracts") / "contracts.py"), config_path)
    assert len(specs) == 1
    assert specs[0].table_name == "orders"
    assert "id" in specs[0].columns
    assert specs[0].columns["id"].dtype is int
    assert specs[0].columns["id"].nullable is False
    assert "created_at" in specs[0].columns
    assert specs[0].columns["created_at"].dtype is datetime


def test_load_contracts_nullable_annotation(tmp_path):
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    contracts_file = contracts_dir / "contracts.py"
    contracts_file.write_text(
        "\n".join(
            [
                "from olly.contracts import TableContract",
                "",
                "class T(TableContract):",
                "    __table__ = 'tbl'",
                "",
                "    name: str | None",
                "",
            ]
        )
    )
    config_path = tmp_path / "olly.toml"
    config_path.write_text("")

    specs = load_contracts(str(Path("contracts") / "contracts.py"), config_path)
    assert len(specs) == 1
    assert specs[0].columns["name"].nullable is True
    assert specs[0].columns["name"].dtype is str


def test_load_contracts_connection_name(tmp_path):
    """__connection__ is stored in TableSpec.connection_name."""
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir()
    contracts_file = contracts_dir / "contracts.py"
    contracts_file.write_text(
        "\n".join(
            [
                "from olly.contracts import TableContract",
                "",
                "class A(TableContract):",
                "    __table__ = 'a'",
                "    __connection__ = 'primary'",
                "    id: int",
                "",
                "class B(TableContract):",
                "    __table__ = 'b'",
                "    id: int",
                "",
            ]
        )
    )
    config_path = tmp_path / "olly.toml"
    config_path.write_text("")

    specs = load_contracts(str(Path("contracts") / "contracts.py"), config_path)
    assert len(specs) == 2
    by_name = {s.table_name: s for s in specs}
    assert by_name["a"].connection_name == "primary"
    assert by_name["b"].connection_name is None


def test_contracts_filtered_by_connection():
    """Contracts with a connection_name are skipped for non-matching connections."""
    contracts = [
        TableSpec(
            schema_name="main",
            table_name="orders",
            strict=False,
            columns={"id": ColumnContract(int, nullable=False)},
            connection_name="primary",
        ),
        TableSpec(
            schema_name="main",
            table_name="users",
            strict=False,
            columns={"id": ColumnContract(int, nullable=False)},
            connection_name="analytics",
        ),
        TableSpec(
            schema_name="main",
            table_name="events",
            strict=False,
            columns={"id": ColumnContract(int, nullable=False)},
        ),
    ]
    schema = _schema({"id": dt.Int32(nullable=False)})
    adapter = FakeAdapter(
        {
            ("main", "orders"): schema,
            ("main", "users"): schema,
            ("main", "events"): schema,
        }
    )

    # Filter to "primary" — should include orders (matches) + events (no connection)
    primary_contracts = [
        c for c in contracts if c.connection_name is None or c.connection_name == "primary"
    ]
    findings = check_contracts(primary_contracts, cast(Any, adapter))
    assert len(findings) == 0
    assert len(primary_contracts) == 2

    # Filter to "analytics" — should include users (matches) + events (no connection)
    analytics_contracts = [
        c
        for c in contracts
        if c.connection_name is None or c.connection_name == "analytics"
    ]
    assert len(analytics_contracts) == 2


class TestTypeCompatible:
    """Unit tests for _type_compatible covering all Ibis type variants."""

    # --- int ---

    @pytest.mark.parametrize("ibis_type", [dt.Int8, dt.Int16, dt.Int32, dt.Int64])
    def test_int_signed(self, ibis_type):
        assert _type_compatible(int, ibis_type(nullable=False))

    @pytest.mark.parametrize("ibis_type", [dt.UInt8, dt.UInt16, dt.UInt32, dt.UInt64])
    def test_int_unsigned(self, ibis_type):
        assert _type_compatible(int, ibis_type(nullable=False))

    def test_int_rejects_float(self):
        assert not _type_compatible(int, dt.Float64(nullable=False))

    # --- float ---

    @pytest.mark.parametrize("ibis_type", [dt.Float16, dt.Float32, dt.Float64])
    def test_float_variants(self, ibis_type):
        assert _type_compatible(float, ibis_type(nullable=False))

    def test_float_rejects_int(self):
        assert not _type_compatible(float, dt.Int64(nullable=False))

    # --- str ---

    def test_str_string(self):
        assert _type_compatible(str, dt.String(nullable=False))

    def test_str_rejects_int(self):
        assert not _type_compatible(str, dt.Int64(nullable=False))

    # --- bool ---

    def test_bool_boolean(self):
        assert _type_compatible(bool, dt.Boolean(nullable=False))

    def test_bool_rejects_int(self):
        assert not _type_compatible(bool, dt.Int64(nullable=False))

    # --- datetime ---

    def test_datetime_timestamp(self):
        assert _type_compatible(datetime, dt.Timestamp(nullable=False))

    def test_datetime_rejects_int(self):
        assert not _type_compatible(datetime, dt.Int64(nullable=False))

    # --- date ---

    def test_date_date(self):
        assert _type_compatible(date, dt.Date(nullable=False))

    def test_date_rejects_str(self):
        assert not _type_compatible(date, dt.String(nullable=False))

    # --- unsupported ---

    def test_unsupported_type_returns_false(self):
        assert not _type_compatible(bytes, dt.String(nullable=False))


def test_contracts_integration(backend):
    """Integration test using the real DuckDB backend from conftest."""
    contracts = [
        TableSpec(
            schema_name="main",
            table_name="orders",
            strict=False,
            columns={
                "id": ColumnContract(int, nullable=False),
                "customer_id": ColumnContract(int, nullable=False),
                "amount": ColumnContract(float, nullable=False),
                "created_at": ColumnContract(datetime, nullable=False),
                "updated_at": ColumnContract(datetime, nullable=False),
            },
        )
    ]
    findings = check_contracts(contracts, backend)
    assert len(findings) == 0


def test_contracts_integration_type_mismatch(backend):
    """Integration: int contract on a float column should produce a type_mismatch."""
    contracts = [
        TableSpec(
            schema_name="main",
            table_name="orders",
            strict=False,
            columns={
                "amount": ColumnContract(int, nullable=False),
            },
        )
    ]
    findings = check_contracts(contracts, backend)
    type_findings = [f for f in findings if f.details.get("issue") == "type_mismatch"]
    assert len(type_findings) == 1
    assert type_findings[0].details["column"] == "amount"
