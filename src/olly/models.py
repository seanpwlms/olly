from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class WindowOp(str, Enum):
    """Operator type for an integrity check time window."""

    GT_NOW = "gt_now"
    BETWEEN = "between"
    EQ_TS = "eq_ts"
    EQ_DATE = "eq_date"


class Disposition(str, Enum):
    """Workflow status for a finding disposition."""

    NOT_STARTED = "not_started"
    NO_ACTION = "no_action"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class IntegrityMethod(str, Enum):
    """Comparison method used for cross-source integrity checks."""

    PK = "pk"
    HASH = "hash"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"


@dataclass
class ColumnInfo:
    """Metadata for a single table column."""

    column_name: str
    data_type: str
    is_nullable: bool


@dataclass
class TableInfo:
    """Schema metadata for a table or view, including its columns."""

    schema_name: str
    table_name: str
    table_type: str  # "TABLE" or "VIEW"
    columns: list[ColumnInfo]


@dataclass
class VolumeRecord:
    """Row count captured for a table during a snapshot."""

    schema_name: str
    table_name: str
    row_count: int


@dataclass
class UsageRecord:
    """Last query timestamp for a table from warehouse query history."""

    schema_name: str
    table_name: str
    last_queried_at: datetime | None  # None = never queried in lookback window


@dataclass
class CostRecord:
    """Query cost data aggregated per table and user from warehouse metadata."""

    schema_name: str
    table_name: str
    user_email: str
    total_bytes_billed: int
    estimated_cost_usd: float
    query_count: int


@dataclass
class Finding:
    """A single data-quality issue detected by a check."""

    check_type: str  # "schema", "volume", "freshness"
    severity: str  # "warning", "error"
    schema_name: str
    table_name: str
    description: str
    details: dict = field(default_factory=dict)
    connection_name: str = ""
    id: int | None = None
    disposition: str = "not_started"
    created_at: str = ""


@dataclass
class WindowSpec:
    """Time-window specification for filtering rows in integrity checks."""

    op: WindowOp
    duration: str | None = None
    start: str | None = None
    end: str | None = None
    value: str | None = None


@dataclass
class Sync:
    """Configuration for a cross-source data integrity sync check."""

    name: str
    source: str
    target: str
    source_table: str
    target_table: str
    method: IntegrityMethod
    key: str | None = None
    hash_columns: list[str] | None = None
    watermark: str | None = None
    window: WindowSpec | None = None
    where: str | None = None
    tolerance_delta: int | None = None
    tolerance_ratio: float | None = None
    tolerance_mode: str | None = None
    severity: str = "error"


@dataclass
class DbtFinding:
    """A finding from a dbt run_results.json artifact."""

    resource_type: str  # "model", "test", "snapshot", "seed"
    severity: str  # "warning", "error"
    unique_id: str  # "model.project.orders"
    status: str  # "error", "fail", "warn", "skipped"
    execution_time: float
    description: str
    details: dict = field(default_factory=dict)
