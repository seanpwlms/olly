import { Link } from "@tanstack/react-router";
import { useConnection } from "../hooks/useConnection";
import { useFindings, useOverview } from "../hooks/queries";
import { ErrorState } from "../components/ErrorState";
import { SkeletonTable } from "../components/Skeleton";
import { FindingsTrendChart } from "../components/FindingsTrendChart";
import { DataTable, type Column } from "../components/DataTable";
import { TableRef } from "../components/TableRef";
import {
  findingColumns,
  findingExpanded,
  findingRowKey,
} from "../components/FindingsTable";
import type { DispositionCounts, Finding, OverviewResponse, TableRow } from "../types";

/** Most untriaged findings shown on the overview before "View all". */
const ATTENTION_LIMIT = 6;

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

const sectionHeading = "text-lg font-semibold text-gray-900 dark:text-gray-100";
const sectionLink = "text-sm text-accent-700 dark:text-accent-300 hover:underline";

/**
 * Net change against the previous run. These are totals, not a per-finding
 * diff, so the copy says "more/fewer than", never "new".
 */
function changeSentence(
  current: { error_count: number; warning_count: number },
  prev: { error_count: number; warning_count: number } | null,
): string | null {
  if (!prev) return null;
  const parts: string[] = [];
  for (const [now, before, word] of [
    [current.error_count, prev.error_count, "error"],
    [current.warning_count, prev.warning_count, "warning"],
  ] as const) {
    const diff = now - before;
    if (diff !== 0) parts.push(`${plural(Math.abs(diff), word)} ${diff > 0 ? "more" : "fewer"}`);
  }
  return parts.length ? `${parts.join(", ")} than the previous check.` : "No change since the previous check.";
}

function Summary({ data }: { data: OverviewResponse }) {
  const { stats, prev_stats } = data;
  const healthy = stats.error_count === 0 && stats.warning_count === 0;
  const change = changeSentence(stats, prev_stats);

  return (
    <header className="mb-8">
      <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Overview</h1>
      {healthy ? (
        <p className="mt-2 flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <svg className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M16.7 5.3a1 1 0 0 1 0 1.4l-8 8a1 1 0 0 1-1.4 0l-4-4a1 1 0 1 1 1.4-1.4L8 12.58l7.3-7.3a1 1 0 0 1 1.4 0Z" clipRule="evenodd" />
          </svg>
          <span>
            <span className="font-medium text-emerald-700 dark:text-emerald-400">All checks passing</span>
            <span className="mx-2 text-gray-300 dark:text-gray-600" aria-hidden="true">·</span>
            {stats.tables_monitored.toLocaleString()} tables monitored
          </span>
        </p>
      ) : (
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          {stats.error_count > 0 && (
            <Link to="/findings" search={{ severity: "error" }} className="font-medium text-red-600 dark:text-red-400 hover:underline">
              {plural(stats.error_count, "error")}
            </Link>
          )}
          {stats.error_count > 0 && stats.warning_count > 0 && (
            <span className="mx-2 text-gray-300 dark:text-gray-600" aria-hidden="true">·</span>
          )}
          {stats.warning_count > 0 && (
            <Link to="/findings" search={{ severity: "warning" }} className="font-medium text-amber-700 dark:text-amber-400 hover:underline">
              {plural(stats.warning_count, "warning")}
            </Link>
          )}
          <span className="mx-2 text-gray-300 dark:text-gray-600" aria-hidden="true">·</span>
          {stats.tables_monitored.toLocaleString()} tables monitored
          {change && <span className="block mt-1">{change}</span>}
        </p>
      )}
    </header>
  );
}

/** "12 untriaged · 3 in progress · 5 completed", each linking to that slice of Findings. */
function StatusCounts({ counts }: { counts: DispositionCounts }) {
  const items = [
    { key: "not_started", text: `${counts.not_started} untriaged` },
    { key: "in_progress", text: `${counts.in_progress} in progress` },
    { key: "completed", text: `${counts.completed} completed` },
    { key: "no_action", text: `${counts.no_action} no action` },
  ].filter((item, i) => i === 0 || !item.text.startsWith("0 "));
  return (
    <span className="text-sm text-gray-500 dark:text-gray-400">
      {items.map((item, i) => (
        <span key={item.key}>
          {i > 0 && <span className="mx-2 text-gray-300 dark:text-gray-600" aria-hidden="true">·</span>}
          <Link to="/findings" search={{ disposition: item.key }} className="hover:underline hover:text-gray-900 dark:hover:text-gray-100">
            {item.text}
          </Link>
        </span>
      ))}
    </span>
  );
}

/**
 * Untriaged findings, errors first. Two small queries (errors, then warnings)
 * so a long list of warnings can never push the errors off the first page.
 */
function NeedsAttention({ connection, counts }: { connection: string; counts: DispositionCounts }) {
  const errors = useFindings({ connection, disposition: "not_started", severity: "error" });
  const warnings = useFindings({ connection, disposition: "not_started", severity: "warning" });

  const columns = findingColumns({ table: true }).filter((c) => c.key !== "when");

  let body;
  if (errors.isError || warnings.isError) {
    body = <ErrorState message="Failed to load findings." onRetry={() => { void errors.refetch(); void warnings.refetch(); }} />;
  } else if (!errors.data || !warnings.data) {
    body = <SkeletonTable rows={4} cols={4} />;
  } else {
    const untriaged: Finding[] = [...errors.data.findings, ...warnings.data.findings].slice(0, ATTENTION_LIMIT);
    const total = errors.data.total + warnings.data.total;
    body =
      untriaged.length === 0 ? (
        <p className="py-6 text-sm text-gray-500 dark:text-gray-400">
          Every finding has a status. Nothing is waiting for triage.
        </p>
      ) : (
        <>
          <DataTable
            data={untriaged}
            columns={columns}
            rowKey={findingRowKey}
            expandedContent={findingExpanded}
            className="mb-2"
          />
          {total > untriaged.length && (
            <Link to="/findings" search={{ disposition: "not_started" }} className={sectionLink}>
              View all {total} untriaged findings
            </Link>
          )}
        </>
      );
  }

  return (
    <section className="mb-10">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className={sectionHeading}>Needs attention</h2>
        <StatusCounts counts={counts} />
      </div>
      {body}
    </section>
  );
}

const tableColumns: Column<TableRow>[] = [
  { key: "table", header: "Table", render: (t) => <TableRef schema={t.schema} table={t.table} /> },
  {
    key: "issues",
    header: "Open issues",
    align: "right",
    render: (t) => (
      <span className="whitespace-nowrap">
        {t.error_count > 0 && (
          <span className="font-medium text-red-600 dark:text-red-400">{plural(t.error_count, "error")}</span>
        )}
        {t.error_count > 0 && t.warning_count > 0 && <span className="text-gray-500 dark:text-gray-400">, </span>}
        {t.warning_count > 0 && (
          <span className="font-medium text-amber-700 dark:text-amber-400">{plural(t.warning_count, "warning")}</span>
        )}
      </span>
    ),
  },
];

function TablesWithIssues({ tables }: { tables: TableRow[] }) {
  if (tables.length === 0) return null;
  return (
    <section className="mb-10">
      <div className="mb-3 flex items-baseline justify-between gap-4">
        <h2 className={sectionHeading}>Tables with issues</h2>
        <Link to="/tables" className={sectionLink}>All tables</Link>
      </div>
      <DataTable data={tables} columns={tableColumns} rowKey={(t) => `${t.schema}.${t.table}`} className="" />
    </section>
  );
}

/** dbt and per-connection status as one line each, linking to their pages. */
function Elsewhere({ data }: { data: OverviewResponse }) {
  const { dbt_stats, findings_by_connection } = data;
  const connections = Object.entries(findings_by_connection);
  const dbtIssues = dbt_stats.error_count + dbt_stats.warning_count;
  if (dbtIssues === 0 && connections.length <= 1) return null;

  return (
    <ul className="mb-8 space-y-1.5 text-sm text-gray-600 dark:text-gray-400">
      {dbtIssues > 0 && (
        <li>
          <Link to="/dbt" className="hover:underline">
            dbt:{" "}
            {dbt_stats.error_count > 0 && (
              <span className="font-medium text-red-600 dark:text-red-400">{plural(dbt_stats.error_count, "failure")}</span>
            )}
            {dbt_stats.error_count > 0 && dbt_stats.warning_count > 0 && ", "}
            {dbt_stats.warning_count > 0 && (
              <span className="font-medium text-amber-700 dark:text-amber-400">{plural(dbt_stats.warning_count, "warning")}</span>
            )}{" "}
            in the latest run
          </Link>
        </li>
      )}
      {connections.length > 1 &&
        connections.map(([conn, counts]) => (
          <li key={conn}>
            <Link to="/findings" search={{ connection: conn }} className="hover:underline">
              <span className="font-mono">{conn}</span>:{" "}
              {counts.errors === 0 && counts.warnings === 0
                ? "no issues"
                : [counts.errors > 0 && plural(counts.errors, "error"), counts.warnings > 0 && plural(counts.warnings, "warning")]
                    .filter(Boolean)
                    .join(", ")}
            </Link>
          </li>
        ))}
    </ul>
  );
}

export function IndexPage() {
  const { connection } = useConnection();
  const { data, isLoading, isError, refetch } = useOverview(connection);

  if (isError) return <ErrorState message="Failed to load dashboard data." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <SkeletonTable rows={6} cols={4} />;

  const healthy = data.stats.error_count === 0 && data.stats.warning_count === 0;

  return (
    <>
      <Summary data={data} />
      {!healthy && (
        <>
          <NeedsAttention connection={connection} counts={data.disposition_counts} />
          <TablesWithIssues tables={data.top_tables} />
        </>
      )}
      <Elsewhere data={data} />
      <FindingsTrendChart data={data.findings_trend} />
    </>
  );
}
