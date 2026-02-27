import { Link } from "@tanstack/react-router";
import { useConnection } from "../hooks/useConnection";
import { useOverview } from "../hooks/queries";
import { StatCard } from "../components/StatCard";
import { StatsRow } from "../components/StatsRow";
import { ErrorState } from "../components/ErrorState";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

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
  if (isLoading || !data) return <div className="text-center text-gray-500 py-8">Loading...</div>;

  const { stats, dbt_stats, findings_by_connection, findings_trend, top_tables, prev_stats } = data;

  const errorTrend = formatTrend(stats.error_count, prev_stats?.error_count);
  const warningTrend = formatTrend(stats.warning_count, prev_stats?.warning_count);

  const trendData = findings_trend.map((p) => ({
    ...p,
    label: p.timestamp.slice(5),
  }));

  return (
    <>
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
            link={{ to: "/dbt" }}
          />
        )}
      </StatsRow>

      {Object.keys(findings_by_connection).length > 1 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Findings by Connection</h2>
          <StatsRow>
            {Object.entries(findings_by_connection).map(([conn, counts]) => (
              <Link
                key={conn}
                to="/findings"
                search={{ connection: conn }}
                className="no-underline text-inherit block flex-1 min-w-[140px]"
              >
                <div className="bg-white rounded-lg border border-gray-200 shadow-sm px-5 py-4 hover:shadow-md transition-shadow">
                  <div className="text-xs text-gray-500 uppercase tracking-wide">{conn}</div>
                  <div className="flex gap-2 mt-1.5">
                    {counts.errors > 0 && (
                      <span className="text-sm font-semibold text-red-600">
                        {counts.errors} error{counts.errors !== 1 ? "s" : ""}
                      </span>
                    )}
                    {counts.warnings > 0 && (
                      <span className="text-sm font-semibold text-amber-600">
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

      {trendData.length > 1 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Findings Trend</h2>
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <Tooltip />
                <Legend />
                <Area type="monotone" dataKey="errors" name="Errors" stroke="#ef4444" fill="#fee2e2" strokeWidth={2} />
                <Area type="monotone" dataKey="warnings" name="Warnings" stroke="#f59e0b" fill="#fef3c7" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {top_tables.length > 0 && (
        <section className="mb-6">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-lg font-semibold text-gray-800">Tables with Issues</h2>
            <Link to="/tables" className="text-sm text-blue-600 hover:underline">View all</Link>
          </div>
          <table className="w-full bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Table</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Errors</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Warnings</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Rows</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {top_tables.map((t) => (
                <tr key={`${t.schema}.${t.table}`} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-sm">
                    <Link
                      to="/table/$schema/$table"
                      params={{ schema: t.schema, table: t.table }}
                      className="text-blue-600 hover:text-blue-800 hover:underline"
                    >
                      {t.schema}.{t.table}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm text-right">
                    {t.error_count > 0 ? <span className="text-red-600 font-semibold">{t.error_count}</span> : <span className="text-gray-300">0</span>}
                  </td>
                  <td className="px-4 py-3 text-sm text-right">
                    {t.warning_count > 0 ? <span className="text-amber-600 font-semibold">{t.warning_count}</span> : <span className="text-gray-300">0</span>}
                  </td>
                  <td className="px-4 py-3 text-sm text-right text-gray-600">
                    {t.row_count != null ? t.row_count.toLocaleString() : "\u2014"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <p className="text-xs text-gray-500">
        Last check:{" "}
        {stats.last_check_time
          ? stats.last_check_time.slice(0, 16).replace("T", " ")
          : "\u2014"}
      </p>
    </>
  );
}
