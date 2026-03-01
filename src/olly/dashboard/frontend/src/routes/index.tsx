import { Link } from "@tanstack/react-router";
import { useConnection } from "../hooks/useConnection";
import { useOverview } from "../hooks/queries";
import { StatCard } from "../components/StatCard";
import { StatsRow } from "../components/StatsRow";
import { ErrorState } from "../components/ErrorState";
import { SkeletonStatCards, SkeletonChart, SkeletonTable } from "../components/Skeleton";
import { DispositionBar } from "../components/DispositionBar";
import { FindingsTrendChart } from "../components/FindingsTrendChart";

function formatTrend(current: number, previous: number | undefined): { trend: string; direction: "up" | "down" | "flat" } {
  if (previous === undefined) return { trend: "", direction: "flat" };
  const diff = current - previous;
  if (diff === 0) return { trend: "No change", direction: "flat" };
  const abs = Math.abs(diff);
  const word = diff > 0 ? "more" : "fewer";
  return {
    trend: `${abs} ${word} since last check`,
    direction: diff > 0 ? "up" : "down",
  };
}

export function IndexPage() {
  const { connection } = useConnection();
  const { data, isLoading, isError, refetch } = useOverview(connection);

  if (isError) return <ErrorState message="Failed to load dashboard data." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <><SkeletonStatCards count={3} /><SkeletonChart /><SkeletonTable rows={5} cols={4} /></>;

  const { stats, dbt_stats, findings_by_connection, findings_trend, top_tables, prev_stats, disposition_counts } = data;

  const errorTrend = formatTrend(stats.error_count, prev_stats?.error_count);
  const warningTrend = formatTrend(stats.warning_count, prev_stats?.warning_count);

  const isHealthy = stats.error_count === 0 && stats.warning_count === 0;

  return (
    <>
      {isHealthy && (
        <div className="flex items-center gap-3 rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950 px-5 py-4 mb-4">
          <svg className="h-5 w-5 text-emerald-600 dark:text-emerald-400 shrink-0" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
          </svg>
          <div>
            <span className="text-sm font-medium text-emerald-800 dark:text-emerald-300">All checks passing</span>
            {stats.last_check_time && (
              <span className="text-xs text-emerald-600 dark:text-emerald-400 ml-2">
                Last check: {stats.last_check_time.slice(0, 16).replace("T", " ")}
              </span>
            )}
          </div>
        </div>
      )}

      <StatsRow>
        <StatCard
          value={stats.error_count}
          label="Errors"
          variant="error"
          link={{ to: "/findings", search: { severity: "error" } }}
          trend={errorTrend.trend}
          trendDirection={errorTrend.direction}
        />
        <StatCard
          value={stats.warning_count}
          label="Warnings"
          variant="warning"
          link={{ to: "/findings", search: { severity: "warning" } }}
          trend={warningTrend.trend}
          trendDirection={warningTrend.direction}
        />
        <StatCard value={stats.tables_monitored} label="Tables Monitored" link={{ to: "/tables" }} />
        {(dbt_stats.error_count > 0 || dbt_stats.warning_count > 0) && (
          <StatCard
            value={dbt_stats.error_count + dbt_stats.warning_count}
            label="dbt Issues"
            variant={dbt_stats.error_count > 0 ? "error" : "warning"}
            link={{ to: "/findings", search: { tab: "dbt" } }}
          />
        )}
      </StatsRow>

      {!isHealthy && disposition_counts && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Disposition Status</h2>
          <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm px-5 py-4">
            <DispositionBar counts={disposition_counts} />
          </div>
        </section>
      )}

      {Object.keys(findings_by_connection).length > 1 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Findings by Connection</h2>
          <StatsRow>
            {Object.entries(findings_by_connection).map(([conn, counts]) => (
              <Link
                key={conn}
                to="/findings"
                search={{ connection: conn }}
                className="no-underline text-inherit block flex-1 min-w-[140px]"
              >
                <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm px-5 py-4 hover:shadow-md transition-shadow">
                  <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">{conn}</div>
                  <div className="flex gap-2 mt-1.5">
                    {counts.errors > 0 && (
                      <span className="text-sm font-semibold text-red-600 dark:text-red-400">
                        {counts.errors} error{counts.errors !== 1 ? "s" : ""}
                      </span>
                    )}
                    {counts.warnings > 0 && (
                      <span className="text-sm font-semibold text-amber-600 dark:text-amber-400">
                        {counts.warnings} warning{counts.warnings !== 1 ? "s" : ""}
                      </span>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </StatsRow>
        </section>
      )}

      <FindingsTrendChart data={findings_trend} />

      {top_tables.length > 0 && (
        <section className="mb-6">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">Tables with Issues</h2>
            <Link to="/tables" className="text-sm text-blue-600 dark:text-blue-400 hover:underline">View all</Link>
          </div>
          <table className="w-full bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Table</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Errors</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Warnings</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Rows</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {top_tables.map((t) => (
                <tr key={`${t.schema}.${t.table}`} className="hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
                  <td className="px-4 py-3 text-sm">
                    <Link
                      to="/table/$schema/$table"
                      params={{ schema: t.schema, table: t.table }}
                      className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
                    >
                      {t.schema}.{t.table}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm text-right">
                    {t.error_count > 0 ? <span className="text-red-600 dark:text-red-400 font-semibold">{t.error_count}</span> : <span className="text-gray-300 dark:text-gray-600">0</span>}
                  </td>
                  <td className="px-4 py-3 text-sm text-right">
                    {t.warning_count > 0 ? <span className="text-amber-600 dark:text-amber-400 font-semibold">{t.warning_count}</span> : <span className="text-gray-300 dark:text-gray-600">0</span>}
                  </td>
                  <td className="px-4 py-3 text-sm text-right text-gray-600 dark:text-gray-400">
                    {t.row_count != null ? t.row_count.toLocaleString() : "\u2014"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <p className="text-xs text-gray-500 dark:text-gray-400">
        Last check:{" "}
        {stats.last_check_time
          ? stats.last_check_time.slice(0, 16).replace("T", " ")
          : "\u2014"}
      </p>
    </>
  );
}
