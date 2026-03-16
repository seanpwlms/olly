export interface DashboardStats {
  error_count: number;
  warning_count: number;
  tables_monitored: number;
  last_check_time: string | null;
}

export interface Finding {
  id: number | null;
  check_type: string;
  severity: string;
  schema_name: string;
  table_name: string;
  description: string;
  details: Record<string, unknown>;
  connection_name: string;
  disposition: string;
  created_at: string;
}

export interface DispositionEvent {
  id: number;
  finding_id: number;
  disposition: string;
  comment: string;
  created_at: string;
  created_by: string;
}

export interface DispositionHistoryResponse {
  finding_id: number;
  current_disposition: string;
  history: DispositionEvent[];
}

export interface DbtFinding {
  resource_type: string;
  severity: string;
  unique_id: string;
  status: string;
  execution_time: number;
  description: string;
  details: Record<string, unknown>;
  dbt_run_id: number | null;
}

export interface DbtPreviousSqlResponse {
  unique_id: string;
  previous_sql: string | null;
}

export interface DbtStats {
  error_count: number;
  warning_count: number;
  pass_count: number;
  total_count: number;
  total_execution_time: number;
  total_failures: number;
}

export interface DbtExecutionLeaderboardEntry {
  unique_id: string;
  resource_type: string;
  execution_time: number;
  status: string;
  severity: string;
}

export interface DbtRunHistoryPoint {
  created_at: string;
  elapsed_time: number;
  total_nodes: number;
  error_count: number;
  warning_count: number;
  pass_count: number;
}

export interface DbtNodeTimingsResponse {
  unique_id: string;
  timings: { timestamp: string; execution_time: number }[];
}

export interface CheckBreakdown {
  check_type: string;
  errors: number;
  warnings: number;
}

export interface FindingsStats {
  total_count: number;
  error_count: number;
  warning_count: number;
  by_check_type: Record<string, [number, number]>;
  by_connection: Record<string, [number, number]>;
  not_started_count: number;
  in_progress_count: number;
  no_action_count: number;
  completed_count: number;
}

export interface ColumnInfo {
  column_name: string;
  data_type: string;
  is_nullable: boolean;
}

export interface TableInfo {
  schema_name: string;
  table_name: string;
  table_type: string;
  columns: ColumnInfo[];
}

export interface VolumeStats {
  current: number | null;
  previous: number | null;
  delta: number | null;
  delta_pct: number | null;
  minimum: number | null;
  maximum: number | null;
  average: number | null;
  snapshot_count: number;
}

export interface TableHistory {
  first_seen: string | null;
  snapshot_count: number;
}

export interface SchemaDiff {
  added: ColumnInfo[];
  removed: ColumnInfo[];
  type_changes: [string, string, string][];
  nullable_changes: [string, boolean, boolean][];
}

export interface TableRow {
  schema: string;
  table: string;
  type: string;
  columns: number;
  row_count: number | null;
  error_count: number;
  warning_count: number;
}

export interface UsageStats {
  unused_count: number;
  stale_count: number;
  total_cost_usd: number | null;
}

export interface LeastUsedTable {
  schema_name: string;
  table_name: string;
  query_count: number;
  estimated_cost_usd: number;
}

export interface CostSummary {
  total_cost_usd: number;
  top_tables?: { schema: string; table: string; cost_usd: number }[];
  top_users?: { user: string; cost_usd: number }[];
}

export interface FindingsTrendPoint {
  timestamp: string;
  errors: number;
  warnings: number;
}

export interface PrevStats {
  error_count: number;
  warning_count: number;
}

// API response types
export interface DispositionCounts {
  not_started: number;
  in_progress: number;
  no_action: number;
  completed: number;
}

export interface OverviewResponse {
  stats: DashboardStats;
  dbt_stats: DbtStats;
  findings_by_connection: Record<
    string,
    { errors: number; warnings: number }
  >;
  findings_trend: FindingsTrendPoint[];
  top_tables: TableRow[];
  prev_stats: PrevStats | null;
  disposition_counts: DispositionCounts;
}

export interface FindingsResponse {
  findings: Finding[];
  stats: FindingsStats;
  filters: {
    check_types: string[];
    severities: string[];
    schemas: string[];
    dispositions: string[];
  };
  page: number;
  total_pages: number;
  total: number;
  last_check_time: string | null;
}

export interface TablesResponse {
  tables: TableRow[];
  page: number;
  total_pages: number;
  total: number;
}

export interface TableDetailResponse {
  table_info: TableInfo | null;
  findings: Finding[];
  volume_stats: VolumeStats;
  volume_timeseries: { snapshot: string; row_count: number }[];
  history: TableHistory;
  schema_diff: SchemaDiff | null;
  contract: ContractStatus | null;
  integrity_syncs: SyncStatus[];
  cost: {
    query_count: number;
    estimated_cost_usd: number;
    top_users: { user: string; cost_usd: number; queries: number }[];
  } | null;
}

export interface UsageResponse {
  stats: UsageStats;
  usage_findings: Finding[];
  cost_summary: CostSummary | null;
  cost_daily: { day: string; cost: number }[];
  least_used: LeastUsedTable[];
}

export interface DbtResponse {
  dbt_stats: DbtStats;
  dbt_findings: DbtFinding[];
  resource_types: string[];
  severities: string[];
  execution_leaderboard: DbtExecutionLeaderboardEntry[];
  run_history: DbtRunHistoryPoint[];
}

export interface ConnectionsResponse {
  connections: string[];
  current: string;
}

export interface ContractColumnStatus {
  column_name: string;
  expected_type: string;
  nullable: boolean;
}

export interface ContractStatus {
  schema_name: string;
  table_name: string;
  strict: boolean;
  connection_name: string | null;
  columns: ContractColumnStatus[];
  status: string;
  findings: Finding[];
}

export interface ContractsResponse {
  contracts: ContractStatus[];
  pass_count: number;
  fail_count: number;
  total_count: number;
  configured: boolean;
  last_check_time: string | null;
}

export interface SyncStatus {
  name: string;
  source: string;
  target: string;
  source_table: string;
  target_table: string;
  method: string;
  key: string | null;
  severity: string;
  status: string;
  findings: Finding[];
}

export interface IntegrityResponse {
  syncs: SyncStatus[];
  pass_count: number;
  fail_count: number;
  total_count: number;
  configured: boolean;
  last_check_time: string | null;
}
