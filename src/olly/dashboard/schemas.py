from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# ── Core model mirrors (from models.py dataclasses) ──


class ColumnInfoModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    column_name: str
    data_type: str
    is_nullable: bool


class TableInfoModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schema_name: str
    table_name: str
    table_type: str
    columns: list[ColumnInfoModel]


class FindingModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    check_type: str
    severity: str
    schema_name: str
    table_name: str
    description: str
    details: dict = {}
    connection_name: str = ""
    id: int | None = None
    disposition: str = "not_started"
    created_at: str = ""


class DbtFindingModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    resource_type: str
    severity: str
    unique_id: str
    status: str
    execution_time: float
    description: str
    details: dict = {}


# ── From data.py dataclasses ──


class VolumeStatsModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    current: int | None
    previous: int | None
    delta: int | None
    delta_pct: float | None
    minimum: int | None
    maximum: int | None
    average: float | None
    snapshot_count: int


class TableHistoryModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    first_seen: str | None
    snapshot_count: int


class SchemaDiffModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    added: list[ColumnInfoModel]
    removed: list[ColumnInfoModel]
    type_changes: list[tuple[str, str, str]]
    nullable_changes: list[tuple[str, bool, bool]]


class FindingsStatsModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_count: int
    error_count: int
    warning_count: int
    by_check_type: dict[str, tuple[int, int]]
    by_connection: dict[str, tuple[int, int]]
    not_started_count: int = 0
    in_progress_count: int = 0
    no_action_count: int = 0
    completed_count: int = 0


class SnapshotInfoModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    snapshot_id: int
    created_at: str
    connection_name: str
    table_count: int


class DashboardStatsModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    error_count: int
    warning_count: int
    tables_monitored: int
    last_check_time: str | None


class DbtStatsModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    error_count: int
    warning_count: int
    pass_count: int
    total_count: int


class UsageStatsModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unused_count: int
    stale_count: int
    total_cost_usd: float | None


class LeastUsedTableModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schema_name: str
    table_name: str
    query_count: int
    estimated_cost_usd: float


class FindingsTrendPointModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: str
    errors: int
    warnings: int


# ── From data_checks.py dataclasses ──


class ContractColumnStatusModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    column_name: str
    expected_type: str
    nullable: bool


class ContractStatusModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schema_name: str
    table_name: str
    strict: bool
    connection_name: str | None
    columns: list[ContractColumnStatusModel]
    status: str
    findings: list[FindingModel]


class SyncStatusModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    source: str
    target: str
    source_table: str
    target_table: str
    method: str
    key: str | None
    severity: str
    status: str
    findings: list[FindingModel]


# ── Response envelopes ──


class ConnectionsResponse(BaseModel):
    connections: list[str]
    current: str


class DispositionCounts(BaseModel):
    not_started: int
    in_progress: int
    no_action: int
    completed: int


class FindingsByConnection(BaseModel):
    errors: int
    warnings: int


class TableRowModel(BaseModel):
    schema_: str
    table: str
    type: str
    columns: int
    row_count: int | None
    error_count: int
    warning_count: int

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_dict(cls, d: dict) -> TableRowModel:
        return cls(
            schema_=d["schema"],
            table=d["table"],
            type=d["type"],
            columns=d["columns"],
            row_count=d["row_count"],
            error_count=d["error_count"],
            warning_count=d["warning_count"],
        )

    def model_dump(self, **kwargs) -> dict:
        d = super().model_dump(**kwargs)
        d["schema"] = d.pop("schema_")
        return d


class PrevStatsModel(BaseModel):
    error_count: int
    warning_count: int


class OverviewResponse(BaseModel):
    stats: DashboardStatsModel
    dbt_stats: DbtStatsModel
    findings_by_connection: dict[str, FindingsByConnection]
    findings_trend: list[FindingsTrendPointModel]
    top_tables: list[TableRowModel]
    prev_stats: PrevStatsModel | None
    disposition_counts: DispositionCounts


class FiltersModel(BaseModel):
    check_types: list[str]
    severities: list[str]
    schemas: list[str]
    dispositions: list[str]


class FindingsResponse(BaseModel):
    findings: list[FindingModel]
    stats: FindingsStatsModel
    filters: FiltersModel
    page: int
    total_pages: int
    total: int
    last_check_time: str | None


class TablesResponse(BaseModel):
    tables: list[TableRowModel]
    page: int
    total_pages: int
    total: int


class CostUserModel(BaseModel):
    user: str
    cost_usd: float
    queries: int


class TableCostModel(BaseModel):
    query_count: int
    estimated_cost_usd: float
    top_users: list[CostUserModel]


class TableDetailResponse(BaseModel):
    table_info: TableInfoModel | None
    findings: list[FindingModel]
    volume_stats: VolumeStatsModel
    volume_timeseries: list[dict]
    history: TableHistoryModel
    schema_diff: SchemaDiffModel | None
    contract: ContractStatusModel | None
    integrity_syncs: list[SyncStatusModel]
    cost: TableCostModel | None


class HistoryResponse(BaseModel):
    snapshots: list[SnapshotInfoModel]
    days: int


class UsageResponse(BaseModel):
    stats: UsageStatsModel
    usage_findings: list[FindingModel]
    cost_summary: dict | None
    cost_daily: list[dict]
    least_used: list[LeastUsedTableModel]


class DbtResponse(BaseModel):
    dbt_stats: DbtStatsModel
    dbt_findings: list[DbtFindingModel]
    resource_types: list[str]
    severities: list[str]


class ContractsResponse(BaseModel):
    contracts: list[ContractStatusModel]
    pass_count: int
    fail_count: int
    total_count: int
    configured: bool
    last_check_time: str | None


class IntegrityResponse(BaseModel):
    syncs: list[SyncStatusModel]
    pass_count: int
    fail_count: int
    total_count: int
    configured: bool
    last_check_time: str | None


class DispositionHistoryResponse(BaseModel):
    finding_id: int
    current_disposition: str
    history: list[dict]
