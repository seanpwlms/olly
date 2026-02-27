import { useParams, Link } from "@tanstack/react-router";
import { useConnection } from "../hooks/useConnection";
import { useTableDetail } from "../hooks/queries";
import { StatCard } from "../components/StatCard";
import { StatsRow } from "../components/StatsRow";
import { Badge } from "../components/Badge";
import { VolumeTrendChart } from "../components/VolumeTrendChart";
import { ErrorState } from "../components/ErrorState";

export function TableDetailPage() {
  const { schema, table } = useParams({ strict: false }) as {
    schema: string;
    table: string;
  };
  const { connection } = useConnection();
  const { data, isLoading, isError, refetch } = useTableDetail(schema, table, connection);

  if (isError) return <ErrorState message="Failed to load table details." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <div className="text-center text-gray-500 py-8">Loading...</div>;

  const { table_info, findings, volume_stats: vol, volume_timeseries, history, schema_diff } = data;

  return (
    <>
      <p className="mb-2">
        <Link to="/" className="text-blue-600 hover:text-blue-800 hover:underline text-sm">
          &larr; Back to dashboard
        </Link>
      </p>
      <h1 className="text-2xl font-bold text-gray-900 mb-4">
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
            <div className="bg-white rounded-lg border border-gray-200 shadow-sm px-5 py-4 flex-1 min-w-[140px]">
              {vol.delta != null ? (
                <div
                  className={`text-2xl font-bold ${vol.delta > 0 ? "text-emerald-600" : vol.delta < 0 ? "text-red-600" : "text-gray-900"}`}
                >
                  {vol.delta > 0 ? "+" : ""}
                  {vol.delta.toLocaleString()}
                  {vol.delta_pct != null && (
                    <span className="text-sm font-normal text-gray-500 ml-1">
                      ({vol.delta_pct > 0 ? "+" : ""}
                      {vol.delta_pct.toFixed(1)}%)
                    </span>
                  )}
                </div>
              ) : (
                <div className="text-2xl font-bold text-gray-900">&mdash;</div>
              )}
              <div className="text-xs text-gray-500 uppercase tracking-wide mt-1">Change</div>
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
        <p className="text-xs text-gray-500 mb-4">
          First seen: {history.first_seen} &middot; {history.snapshot_count} snapshot
          {history.snapshot_count !== 1 ? "s" : ""}
        </p>
      )}

      {findings.length > 0 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Findings</h2>
          <table className="w-full bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden mb-6">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Check</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Severity</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {findings.map((f, i) => (
                <tr key={i} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-sm text-gray-700">{f.check_type}</td>
                  <td className="px-4 py-3">
                    <Badge type={f.severity}>{f.severity}</Badge>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">{f.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {schema_diff && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Schema Changes (since previous snapshot)</h2>
          <table className="w-full bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden mb-6">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Change</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Column</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {schema_diff.added.map((c) => (
                <tr key={`added-${c.column_name}`} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <Badge type="added">added</Badge>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">{c.column_name}</td>
                  <td className="px-4 py-3 text-sm text-gray-700">
                    <code className="bg-gray-100 px-1.5 py-0.5 rounded text-sm">{c.data_type}</code>
                    {c.is_nullable ? ", nullable" : ""}
                  </td>
                </tr>
              ))}
              {schema_diff.removed.map((c) => (
                <tr key={`removed-${c.column_name}`} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <Badge type="removed">removed</Badge>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">{c.column_name}</td>
                  <td className="px-4 py-3 text-sm text-gray-700">
                    <code className="bg-gray-100 px-1.5 py-0.5 rounded text-sm">{c.data_type}</code>
                  </td>
                </tr>
              ))}
              {schema_diff.type_changes.map(([col, oldType, newType]) => (
                <tr key={`type-${col}`} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <Badge type="warning">type changed</Badge>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">{col}</td>
                  <td className="px-4 py-3 text-sm text-gray-700">
                    <code className="bg-gray-100 px-1.5 py-0.5 rounded text-sm">{oldType}</code> &rarr; <code className="bg-gray-100 px-1.5 py-0.5 rounded text-sm">{newType}</code>
                  </td>
                </tr>
              ))}
              {schema_diff.nullable_changes.map(([col, oldNull, newNull]) => (
                <tr key={`null-${col}`} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <Badge type="warning">nullable changed</Badge>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">{col}</td>
                  <td className="px-4 py-3 text-sm text-gray-700">
                    {oldNull ? "nullable" : "not null"} &rarr;{" "}
                    {newNull ? "nullable" : "not null"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <VolumeTrendChart data={volume_timeseries} />

      {table_info && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Schema</h2>
          <table className="w-full bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden mb-6">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Column</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Type</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Nullable</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {table_info.columns.map((c) => (
                <tr key={c.column_name} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-sm text-gray-700">{c.column_name}</td>
                  <td className="px-4 py-3 text-sm">
                    <code className="bg-gray-100 px-1.5 py-0.5 rounded text-sm">{c.data_type}</code>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">{c.is_nullable ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
