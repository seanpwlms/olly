import { useParams } from "@tanstack/react-router";
import { useConnection } from "../hooks/useConnection";
import { useTableDetail } from "../hooks/queries";
import { StatCard } from "../components/StatCard";
import { StatsRow } from "../components/StatsRow";
import { Badge } from "../components/Badge";
import { VolumeTrendChart } from "../components/VolumeTrendChart";
import { ErrorState } from "../components/ErrorState";
import { SkeletonStatCards, SkeletonChart, SkeletonTable } from "../components/Skeleton";
import { DataTable, type Column } from "../components/DataTable";
import type { Finding, ColumnInfo, SyncStatus } from "../types";

interface CostUser {
  user: string;
  cost_usd: number;
  queries: number;
}

interface SchemaDiffRow {
  key: string;
  change: string;
  column: string;
  details: React.ReactNode;
}

export function TableDetailPage() {
  const { schema, table } = useParams({ strict: false }) as {
    schema: string;
    table: string;
  };
  const { connection } = useConnection();
  const { data, isLoading, isError, refetch } = useTableDetail(schema, table, connection);

  if (isError) return <ErrorState message="Failed to load table details." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <><SkeletonStatCards count={4} /><SkeletonChart /><SkeletonTable rows={5} cols={3} /></>;

  const { table_info, findings, volume_stats: vol, volume_timeseries, history, schema_diff, contract, integrity_syncs, cost } = data;

  const findingsColumns: Column<Finding>[] = [
    { key: "check_type", header: "Check", render: (f) => f.check_type },
    { key: "severity", header: "Severity", render: (f) => <Badge type={f.severity}>{f.severity}</Badge> },
    { key: "description", header: "Description", render: (f) => f.description },
  ];

  const integrityColumns: Column<SyncStatus>[] = [
    { key: "name", header: "Sync", render: (s) => s.name },
    { key: "method", header: "Method", render: (s) => <Badge type={s.method}>{s.method}</Badge> },
    {
      key: "tables",
      header: <>Source &rarr; Target</>,
      render: (s) => <>{s.source_table} <span className="text-gray-300 dark:text-gray-600 mx-1">&rarr;</span> {s.target_table}</>,
    },
    { key: "status", header: "Status", render: (s) => <Badge type={s.status}>{s.status}</Badge> },
  ];

  const costUserColumns: Column<CostUser>[] = [
    { key: "user", header: "User", render: (u) => u.user },
    { key: "queries", header: "Queries", render: (u) => u.queries.toLocaleString() },
    { key: "cost_usd", header: "Cost (USD)", render: (u) => `$${u.cost_usd.toFixed(2)}` },
  ];

  const schemaColumns: Column<ColumnInfo>[] = [
    { key: "column_name", header: "Column", render: (c) => c.column_name },
    {
      key: "data_type",
      header: "Type",
      render: (c) => <code className="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-sm">{c.data_type}</code>,
    },
    { key: "is_nullable", header: "Nullable", render: (c) => (c.is_nullable ? "yes" : "no") },
  ];

  // Build schema diff rows
  const schemaDiffRows: SchemaDiffRow[] = [];
  if (schema_diff) {
    for (const c of schema_diff.added) {
      schemaDiffRows.push({
        key: `added-${c.column_name}`,
        change: "added",
        column: c.column_name,
        details: <><code className="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-sm">{c.data_type}</code>{c.is_nullable ? ", nullable" : ""}</>,
      });
    }
    for (const c of schema_diff.removed) {
      schemaDiffRows.push({
        key: `removed-${c.column_name}`,
        change: "removed",
        column: c.column_name,
        details: <code className="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-sm">{c.data_type}</code>,
      });
    }
    for (const [col, oldType, newType] of schema_diff.type_changes) {
      schemaDiffRows.push({
        key: `type-${col}`,
        change: "type changed",
        column: col,
        details: <><code className="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-sm">{oldType}</code> &rarr; <code className="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-sm">{newType}</code></>,
      });
    }
    for (const [col, oldNull, newNull] of schema_diff.nullable_changes) {
      schemaDiffRows.push({
        key: `null-${col}`,
        change: "nullable changed",
        column: col,
        details: <>{oldNull ? "nullable" : "not null"} &rarr; {newNull ? "nullable" : "not null"}</>,
      });
    }
  }

  const schemaDiffColumns: Column<SchemaDiffRow>[] = [
    {
      key: "change",
      header: "Change",
      render: (r) => {
        const badgeType = r.change === "added" ? "added" : r.change === "removed" ? "removed" : "warning";
        return <Badge type={badgeType}>{r.change}</Badge>;
      },
    },
    { key: "column", header: "Column", render: (r) => r.column },
    { key: "details", header: "Details", render: (r) => r.details },
  ];

  return (
    <>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
        {schema}.{table}
      </h1>

      <StatsRow>
        {table_info && (
          <>
            <StatCard value={table_info.table_type} label="Type" />
            <StatCard value={table_info.columns.length} label="Columns" />
          </>
        )}
        {vol && vol.current != null && (
          <>
            <StatCard value={vol.current.toLocaleString()} label="Row Count" />
            <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm px-5 py-4 flex-1 min-w-[140px]">
              {vol.delta != null ? (
                <div
                  className={`text-2xl font-bold ${vol.delta > 0 ? "text-emerald-600 dark:text-emerald-400" : vol.delta < 0 ? "text-red-600 dark:text-red-400" : "text-gray-900 dark:text-white"}`}
                >
                  {vol.delta > 0 ? "+" : ""}
                  {vol.delta.toLocaleString()}
                  {vol.delta_pct != null && (
                    <span className="text-sm font-normal text-gray-500 dark:text-gray-400 ml-1">
                      ({vol.delta_pct > 0 ? "+" : ""}
                      {vol.delta_pct.toFixed(1)}%)
                    </span>
                  )}
                </div>
              ) : (
                <div className="text-2xl font-bold text-gray-900 dark:text-white">&mdash;</div>
              )}
              <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide mt-1">Change</div>
            </div>
          </>
        )}
      </StatsRow>

      {vol && vol.snapshot_count > 1 && (
        <StatsRow>
          {vol.minimum != null && (
            <StatCard value={vol.minimum.toLocaleString()} label="Min Rows" />
          )}
          {vol.maximum != null && (
            <StatCard value={vol.maximum.toLocaleString()} label="Max Rows" />
          )}
          {vol.average != null && (
            <StatCard value={vol.average.toLocaleString()} label="Avg Rows" />
          )}
          <StatCard value={vol.snapshot_count} label="Snapshots" />
        </StatsRow>
      )}

      {history && history.first_seen && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          First seen: {history.first_seen} &middot; {history.snapshot_count} snapshot
          {history.snapshot_count !== 1 ? "s" : ""}
        </p>
      )}

      {findings.length > 0 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Findings</h2>
          <DataTable
            data={findings}
            columns={findingsColumns}
            rowKey={(f) => `${f.check_type}-${f.description}`}
            rowBorderColor={(f) =>
              f.severity === "error" ? "error" : f.severity === "warning" ? "warning" : "success"
            }
          />
        </section>
      )}

      {contract && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Contract Status</h2>
          <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm px-5 py-4">
            <div className="flex items-center gap-3 mb-3">
              <Badge type={contract.status}>{contract.status}</Badge>
              {contract.strict && <span className="text-xs text-gray-500 dark:text-gray-400">Strict mode</span>}
              {contract.connection_name && (
                <span className="text-xs text-gray-500 dark:text-gray-400">Connection: {contract.connection_name}</span>
              )}
            </div>
            {contract.columns.length > 0 && (
              <div className="mb-3">
                <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">Expected Columns</h3>
                <div className="grid grid-cols-3 gap-1 text-xs">
                  <span className="font-medium text-gray-500 dark:text-gray-400">Name</span>
                  <span className="font-medium text-gray-500 dark:text-gray-400">Type</span>
                  <span className="font-medium text-gray-500 dark:text-gray-400">Nullable</span>
                  {contract.columns.map((col) => (
                    <div key={col.column_name} className="contents">
                      <span className="text-gray-700 dark:text-gray-300">{col.column_name}</span>
                      <span className="text-gray-500 dark:text-gray-400">{col.expected_type}</span>
                      <span className="text-gray-500 dark:text-gray-400">{col.nullable ? "yes" : "no"}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {contract.findings.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">Violations</h3>
                <ul className="space-y-1">
                  {contract.findings.map((f, i) => (
                    <li key={i} className="text-xs text-gray-600 dark:text-gray-400">
                      <Badge type={f.severity}>{f.severity}</Badge>
                      <span className="ml-2">{f.description}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}

      {integrity_syncs && integrity_syncs.length > 0 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Integrity</h2>
          <DataTable
            data={integrity_syncs}
            columns={integrityColumns}
            rowKey={(s) => s.name}
          />
        </section>
      )}

      {cost && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Usage &amp; Cost</h2>
          <StatsRow>
            <StatCard value={cost.query_count.toLocaleString()} label="Total Queries" />
            <StatCard value={`$${cost.estimated_cost_usd.toFixed(2)}`} label="Estimated Cost" />
          </StatsRow>
          {cost.top_users.length > 0 && (
            <div className="mt-3">
              <DataTable
                data={cost.top_users}
                columns={costUserColumns}
                rowKey={(u) => u.user}
              />
            </div>
          )}
        </section>
      )}

      {schema_diff && schemaDiffRows.length > 0 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Schema Changes (since previous snapshot)</h2>
          <DataTable
            data={schemaDiffRows}
            columns={schemaDiffColumns}
            rowKey={(r) => r.key}
          />
        </section>
      )}

      <VolumeTrendChart
        data={volume_timeseries}
        findings={findings}
        schemaDiffTimestamp={history?.first_seen && schema_diff ? volume_timeseries[volume_timeseries.length - 1]?.snapshot : null}
      />

      {table_info && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Schema</h2>
          <DataTable
            data={table_info.columns}
            columns={schemaColumns}
            rowKey={(c) => c.column_name}
          />
        </section>
      )}
    </>
  );
}
