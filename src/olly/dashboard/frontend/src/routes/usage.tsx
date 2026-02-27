import { Link } from "@tanstack/react-router";
import { useConnection } from "../hooks/useConnection";
import { useUsage } from "../hooks/queries";
import { StatCard } from "../components/StatCard";
import { StatsRow } from "../components/StatsRow";
import { Badge } from "../components/Badge";
import { EmptyState } from "../components/EmptyState";
import { CostDailyChart } from "../components/CostDailyChart";
import { ErrorState } from "../components/ErrorState";

export function UsagePage() {
  const { connection } = useConnection();
  const { data, isLoading, isError, refetch } = useUsage(connection);

  if (isError) return <ErrorState message="Failed to load usage data." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <div className="text-center text-gray-500 py-8">Loading...</div>;

  const { stats, usage_findings, cost_summary, cost_daily, least_used } = data;

  return (
    <>
      <h1 className="text-2xl font-bold text-gray-900 mb-4">Usage &amp; Cost</h1>

      <StatsRow>
        <StatCard value={stats.unused_count} label="Unused Tables" variant="error" />
        <StatCard value={stats.stale_count} label="Stale Tables" variant="warning" />
        {stats.total_cost_usd != null && (
          <StatCard
            value={`$${stats.total_cost_usd.toFixed(2)}`}
            label="Total Cost (USD)"
          />
        )}
      </StatsRow>

      <section className="mb-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-3">Unused &amp; Stale Tables</h2>
        {usage_findings.length > 0 ? (
          <table className="w-full bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden mb-6">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Table</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Last Queried</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Days Inactive</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {usage_findings.map((f, i) => (
                <tr key={i} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-sm">
                    <Link
                      to="/table/$schema/$table"
                      params={{ schema: f.schema_name, table: f.table_name }}
                      className="text-blue-600 hover:text-blue-800 hover:underline"
                    >
                      {f.schema_name}.{f.table_name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    {f.details.last_queried_at == null ? (
                      <Badge type="unused">unused</Badge>
                    ) : (
                      <Badge type="stale">stale</Badge>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">
                    {f.details.last_queried_at
                      ? String(f.details.last_queried_at).slice(0, 10)
                      : "\u2014"}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">
                    {f.details.days_unused != null
                      ? Math.floor(f.details.days_unused as number)
                      : "\u2014"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState message="No unused or stale tables detected." />
        )}
      </section>

      {least_used.length > 0 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Top 10 Least Used Tables</h2>
          <table className="w-full bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden mb-6">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Table</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Query Count</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Cost (USD)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {least_used.map((t) => (
                <tr key={`${t.schema_name}.${t.table_name}`} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-sm">
                    <Link
                      to="/table/$schema/$table"
                      params={{ schema: t.schema_name, table: t.table_name }}
                      className="text-blue-600 hover:text-blue-800 hover:underline"
                    >
                      {t.schema_name}.{t.table_name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">{t.query_count}</td>
                  <td className="px-4 py-3 text-sm text-gray-700">${t.estimated_cost_usd.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {cost_summary && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Cost Breakdown</h2>

          <CostDailyChart data={cost_daily} />

          {cost_summary.top_tables && cost_summary.top_tables.length > 0 && (
            <>
              <h3 className="text-base font-semibold text-gray-700 mb-2 mt-4">Top Tables by Cost</h3>
              <table className="w-full bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden mb-6">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Table</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Cost (USD)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {cost_summary.top_tables.map((t) => (
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
                      <td className="px-4 py-3 text-sm text-gray-700">${t.cost_usd.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {cost_summary.top_users && cost_summary.top_users.length > 0 && (
            <>
              <h3 className="text-base font-semibold text-gray-700 mb-2 mt-4">Top Users by Cost</h3>
              <table className="w-full bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden mb-6">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">User</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Cost (USD)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {cost_summary.top_users.map((u) => (
                    <tr key={u.user} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3 text-sm text-gray-700">{u.user}</td>
                      <td className="px-4 py-3 text-sm text-gray-700">${u.cost_usd.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>
      )}
    </>
  );
}
