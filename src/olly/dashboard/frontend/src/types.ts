export interface DashboardStats {
  error_count: number;
  warning_count: number;
  tables_monitored: number;
  last_check_time: string | null;
}

export interface Finding {
  check_type: string;
  severity: string;
  schema_name: string;
  table_name: string;
  description: string;
  details: Record<string, unknown>;
  connection_name: string;
}

export interface DbtFinding {
  resource_type: string;
  severity: string;
  unique_id: string;
  status: string;
  execution_time: number;
  description: string;
  details: Record<string, unknown>;
}

export interface DbtStats {
  error_count: number;
  warning_count: number;
  pass_count: number;
  total_count: number;
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
}

export interface FindingsResponse {
  findings: Finding[];
  stats: FindingsStats;
  filters: {
    check_types: string[];
    severities: string[];
    schemas: string[];
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
}

export interface ConnectionsResponse {
  connections: string[];
  current: string;
}
