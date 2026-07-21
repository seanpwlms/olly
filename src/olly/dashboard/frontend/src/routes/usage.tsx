import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useConnection } from "../hooks/useConnection";
import { useUsage } from "../hooks/queries";
import { StatCard } from "../components/StatCard";
import { StatsRow } from "../components/StatsRow";
import { Badge } from "../components/Badge";
import { EmptyState } from "../components/EmptyState";
import { CostDailyChart } from "../components/CostDailyChart";
import { ErrorState } from "../components/ErrorState";
import { SkeletonStatCards, SkeletonChart, SkeletonTable } from "../components/Skeleton";
import { DataTable, type Column } from "../components/DataTable";
import { Pagination } from "../components/Pagination";
import type { Finding, LeastUsedTable } from "../types";

interface CostTable {
  schema: string;
  table: string;
  cost_usd: number;
}

interface CostUser {
  user: string;
  cost_usd: number;
}

export function UsagePage() {
  const { connection } = useConnection();
  const { data, isLoading, isError, refetch } = useUsage(connection);
  const [usagePage, setUsagePage] = useState(1);

  if (isError) return <ErrorState message="Failed to load usage data." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <><SkeletonStatCards count={3} /><SkeletonChart /><SkeletonTable rows={5} cols={4} /></>;

  const { stats, usage_findings, cost_summary, cost_daily, least_used } = data;

  const schemaFindings = usage_findings.filter((f) => f.details.scope === "schema");
  const tableFindings = usage_findings.filter((f) => f.details.scope !== "schema");

  const PAGE_SIZE = 25;
  const usageTotalPages = Math.ceil(tableFindings.length / PAGE_SIZE);
  const pagedFindings = tableFindings.slice((usagePage - 1) * PAGE_SIZE, usagePage * PAGE_SIZE);

  const schemaFindingsColumns: Column<Finding>[] = [
    { key: "schema", header: "Schema", render: (f) => f.schema_name },
    {
      key: "tables",
      header: "Tables",
      render: (f) => String(f.details.table_count ?? "—"),
    },
    {
      key: "unused",
      header: "Unused",
      render: (f) => String(f.details.unused_count ?? "—"),
    },
    {
      key: "stale",
      header: "Stale",
      render: (f) => String(f.details.stale_count ?? "—"),
    },
    {
      key: "inactive_pct",
      header: "% Inactive",
      render: (f) =>
        f.details.inactive_pct != null ? (
          <Badge type={(f.details.inactive_pct as number) >= 100 ? "unused" : "stale"}>
            {Math.round(f.details.inactive_pct as number)}%
          </Badge>
        ) : (
          "—"
        ),
    },
    {
      key: "last_activity",
      header: "Last Activity",
      render: (f) =>
        f.details.last_activity_at
          ? String(f.details.last_activity_at).slice(0, 10)
          : "—",
    },
  ];

  const usageFindingsColumns: Column<Finding>[] = [
    {
      key: "table",
      header: "Table",
      render: (f) => (
        <Link
          to="/table/$schema/$table"
          params={{ schema: f.schema_name, table: f.table_name }}
          className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
        >
          {f.schema_name}.{f.table_name}
        </Link>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (f) =>
        f.details.last_queried_at == null ? (
          <Badge type="unused">unused</Badge>
        ) : (
          <Badge type="stale">stale</Badge>
        ),
    },
    {
      key: "last_queried",
      header: "Last Queried",
      render: (f) =>
        f.details.last_queried_at
          ? String(f.details.last_queried_at).slice(0, 10)
          : "\u2014",
    },
    {
      key: "days_inactive",
      header: "Days Inactive",
      render: (f) =>
        f.details.days_unused != null
          ? Math.floor(f.details.days_unused as number)
          : "\u2014",
    },
  ];

  const leastUsedColumns: Column<LeastUsedTable>[] = [
    {
      key: "table",
      header: "Table",
      render: (t) => (
        <Link
          to="/table/$schema/$table"
          params={{ schema: t.schema_name, table: t.table_name }}
          className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
        >
          {t.schema_name}.{t.table_name}
        </Link>
      ),
    },
    { key: "query_count", header: "Query Count", render: (t) => t.query_count },
    { key: "cost_usd", header: "Cost (USD)", render: (t) => `$${t.estimated_cost_usd.toFixed(2)}` },
  ];

  const topTableColumns: Column<CostTable>[] = [
    {
      key: "table",
      header: "Table",
      render: (t) => (
        <Link
          to="/table/$schema/$table"
          params={{ schema: t.schema, table: t.table }}
          className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
        >
          {t.schema}.{t.table}
        </Link>
      ),
    },
    { key: "cost_usd", header: "Cost (USD)", render: (t) => `$${t.cost_usd.toFixed(2)}` },
  ];

  const topUserColumns: Column<CostUser>[] = [
    { key: "user", header: "User", render: (u) => u.user },
    { key: "cost_usd", header: "Cost (USD)", render: (u) => `$${u.cost_usd.toFixed(2)}` },
  ];

  return (
    <>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">Usage &amp; Cost</h1>

      <StatsRow>
        {stats.unused_schema_count > 0 && (
          <StatCard value={stats.unused_schema_count} label="Unused Schemas" variant="error" />
        )}
        <StatCard value={stats.unused_count} label="Unused Tables" variant="error" />
        <StatCard value={stats.stale_count} label="Stale Tables" variant="warning" />
        {stats.total_cost_usd != null && (
          <StatCard
            value={`$${stats.total_cost_usd.toFixed(2)}`}
            label="Total Cost (USD)"
          />
        )}
      </StatsRow>

      {cost_summary && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Cost Breakdown</h2>

          <CostDailyChart data={cost_daily} />

          {cost_summary.top_tables && cost_summary.top_tables.length > 0 && (
            <>
              <h3 className="text-base font-semibold text-gray-700 dark:text-gray-300 mb-2 mt-4">Top Tables by Cost</h3>
              <DataTable
                data={cost_summary.top_tables}
                columns={topTableColumns}
                rowKey={(t) => `${t.schema}.${t.table}`}
              />
            </>
          )}

          {cost_summary.top_users && cost_summary.top_users.length > 0 && (
            <>
              <h3 className="text-base font-semibold text-gray-700 dark:text-gray-300 mb-2 mt-4">Top Users by Cost</h3>
              <DataTable
                data={cost_summary.top_users}
                columns={topUserColumns}
                rowKey={(u) => u.user}
              />
            </>
          )}
        </section>
      )}

      {least_used.length > 0 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Top 10 Least Used Tables</h2>
          <DataTable
            data={least_used}
            columns={leastUsedColumns}
            rowKey={(t) => `${t.schema_name}.${t.table_name}`}
          />
        </section>
      )}

      {schemaFindings.length > 0 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">
            Unused Schemas
            <span className="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400">
              ({schemaFindings.length})
            </span>
          </h2>
          <DataTable
            data={schemaFindings}
            columns={schemaFindingsColumns}
            rowKey={(f) => `${f.connection_name}.${f.schema_name}`}
          />
        </section>
      )}

      <section className="mb-6">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">
          Unused &amp; Stale Tables
          {tableFindings.length > 0 && (
            <span className="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400">
              ({tableFindings.length})
            </span>
          )}
        </h2>
        {tableFindings.length > 0 ? (
          <>
            <DataTable
              data={pagedFindings}
              columns={usageFindingsColumns}
              rowKey={(f) => `${f.schema_name}.${f.table_name}`}
            />
            <Pagination page={usagePage} totalPages={usageTotalPages} onPageChange={setUsagePage} />
          </>
        ) : (
          <EmptyState message="No unused or stale tables detected." />
        )}
      </section>
    </>
  );
}
