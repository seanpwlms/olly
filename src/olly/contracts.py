from __future__ import annotations

import types
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Union, get_args, get_origin, get_type_hints

from olly._import import import_module_spec


SUPPORTED_TYPES = {int, float, str, bool, datetime, date, Decimal}


@dataclass(frozen=True)
class ColumnContract:
    """Expected schema for a single column.

    Attributes:
        dtype: Expected Python type (e.g. ``int``, ``float``, ``str``).
        nullable: Whether the column may contain nulls.
    """

    dtype: type
    nullable: bool = True


@dataclass(frozen=True)
class TableSpec:
    """Fully resolved contract for a single table.

    Attributes:
        schema_name: Database schema the table lives in.
        table_name: Name of the table.
        strict: If True, extra columns not in the contract are flagged.
        columns: Mapping of column name to its expected contract.
        connection_name: If set, only check this contract against the named
            connection.  ``None`` means check against all connections.
    """

    schema_name: str
    table_name: str
    strict: bool
    columns: dict[str, ColumnContract]
    connection_name: str | None = None


_registry: list[TableSpec] = []


class TableContract:
    """Declarative base class for defining table contracts.

    Subclasses set ``__schema__``, ``__table__``, and ``__strict__`` class
    attributes and declare columns as Python type annotations::

        class Orders(TableContract):
            __table__ = "orders"
            id: int
            amount: float
            created_at: datetime
            name: str | None  # nullable

    On subclass creation the contract is automatically registered in the
    global ``registry``.
    """

    __schema__ = "main"
    __table__ = None
    __strict__ = False
    __connection__ = None
    __abstract__ = False

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if cls is TableContract:
            return
        if getattr(cls, "__abstract__", False):
            return
        table_name = getattr(cls, "__table__", None)
        if not table_name:
            raise ValueError(f"{cls.__name__} is missing __table__")
        schema_name = getattr(cls, "__schema__", "main") or "main"
        strict = bool(getattr(cls, "__strict__", False))
        connection_name = getattr(cls, "__connection__", None) or None
        columns = _collect_columns(cls)
        _registry.append(
            TableSpec(
                schema_name=schema_name,
                table_name=table_name,
                strict=strict,
                columns=columns,
                connection_name=connection_name,
            )
        )


def load_contracts(
    module_spec: str, config_path: Path | None = None
) -> list[TableSpec]:
    """Import a contracts module and return all registered table specs.

    Args:
        module_spec: Dotted module path or file path to a Python file
            containing ``TableContract`` subclasses.
        config_path: Path to ``olly.toml``, used to resolve relative file
            paths. Defaults to the current working directory.

    Returns:
        List of ``TableSpec`` instances collected from the module.

    Raises:
        ValueError: If *module_spec* is blank or no contracts are found.
    """
    if not module_spec or not module_spec.strip():
        raise ValueError("contracts.module must be set to a module path or file path.")
    _registry.clear()
    import_module_spec(module_spec, config_path, label="contracts")
    specs = list(_registry)
    if not specs:
        raise ValueError(f"No contracts found in {module_spec}")
    return specs


def _unwrap_optional(annotation: type) -> tuple[type, bool]:
    """Unwrap an optional type annotation.

    Returns:
        A tuple of ``(inner_type, is_nullable)``.
        ``int`` → ``(int, False)``, ``int | None`` → ``(int, True)``.
    """
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        args = get_args(annotation)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and type(None) in args:
            return non_none[0], True
    return annotation, False


def _collect_columns(contract_cls: type[TableContract]) -> dict[str, ColumnContract]:
    """Collect column contracts from type annotations on the class."""
    try:
        hints = get_type_hints(contract_cls)
    except Exception:
        hints = {}
    columns: dict[str, ColumnContract] = {}
    for name, annotation in hints.items():
        if name.startswith("_"):
            continue
        inner_type, nullable = _unwrap_optional(annotation)
        if inner_type not in SUPPORTED_TYPES:
            continue
        columns[name] = ColumnContract(dtype=inner_type, nullable=nullable)
    return columns
