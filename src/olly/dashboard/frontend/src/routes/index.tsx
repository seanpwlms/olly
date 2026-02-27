import { Link } from "@tanstack/react-router";
import { useConnection } from "../hooks/useConnection";
import { useOverview, useRefresh } from "../hooks/queries";
import { StatCard } from "../components/StatCard";
import { StatsRow } from "../components/StatsRow";
import { Badge } from "../components/Badge";
import { FindingsTable } from "../components/FindingsTable";
import { useState } from "react";

export function IndexPage() {
  const { connection } = useConnection();
  const { data, isLoading } = useOverview(connection);
  const refresh = useRefresh();
  const [checkFilter, setCheckFilter] = useState("");
  const [sevFilter, setSevFilter] = useState("");
  const [schemaFilter, setSchemaFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  if (isLoading || !data) return <div className="text-center text-gray-500 py-8">Loading...</div>;

  const { stats, dbt_stats, check_breakdown, findings_by_connection, critical_findings, findings, dbt_findings } = data;

  const checkTypes = [...new Set(findings.map((f) => f.check_type))].sort();
  const severities = [...new Set(findings.map((f) => f.severity))].sort();
  const schemas = [...new Set(findings.map((f) => f.schema_name))].sort();

  let filteredFindings = findings;
  if (checkFilter) filteredFindings = filteredFindings.filter((f) => f.check_type === checkFilter);
  if (sevFilter) filteredFindings = filteredFindings.filter((f) => f.severity === sevFilter);
  if (schemaFilter) filteredFindings = filteredFindings.filter((f) => f.schema_name === schemaFilter);
  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    filteredFindings = filteredFindings.filter(
      (f) =>
        f.description.toLowerCase().includes(q) ||
        f.table_name.toLowerCase().includes(q) ||
        f.schema_name.toLowerCase().includes(q),
    );
  }

  return (
    <>
      <StatsRow>
        <StatCard value={stats.error_count} label="Errors" variant="error" />
        <StatCard value={stats.warning_count} label="Warnings" variant="warning" />
        <StatCard value={stats.tables_monitored} label="Tables Monitored" />
        {(dbt_stats.error_count > 0 || dbt_stats.warning_count > 0) && (
          <StatCard
            value={dbt_stats.error_count + dbt_stats.warning_count}
            label="dbt Issues"
            variant={dbt_stats.error_count > 0 ? "error" : "warning"}
            href="/dbt"
          />
        )}
      </StatsRow>

      {Object.keys(findings_by_connection).length > 1 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Findings by Connection</h2>
          <StatsRow>
            {Object.entries(findings_by_connection).map(([conn, counts]) => (
              <a key={conn} href={`/findings?connection=${conn}`} className="no-underline text-inherit block flex-1 min-w-[140px]">
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
              </a>
            ))}
          </StatsRow>
        </section>
      )}

      {check_breakdown.length > 0 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">By Check Type</h2>
          <StatsRow>
            {check_breakdown.map((cb) => (
              <div key={cb.check_type} className="bg-white rounded-lg border border-gray-200 shadow-sm px-5 py-4 flex-1 min-w-[140px]">
                <div className="text-xs text-gray-500 uppercase tracking-wide">{cb.check_type}</div>
                <div className="flex gap-2 mt-1.5">
                  {cb.errors > 0 && (
                    <span className="text-sm font-semibold text-red-600">
                      {cb.errors} error{cb.errors !== 1 ? "s" : ""}
                    </span>
                  )}
                  {cb.warnings > 0 && (
                    <span className="text-sm font-semibold text-amber-600">
                      {cb.warnings} warning{cb.warnings !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </StatsRow>
        </section>
      )}

      {critical_findings.length > 0 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Recent Critical Issues</h2>
          {critical_findings.map((f, i) => (
            <div key={i} className="bg-white rounded-lg border border-gray-200 shadow-sm border-l-4 border-l-red-400 px-5 py-3 mb-2">
              <Badge type={f.severity}>{f.severity}</Badge>{" "}
              <Link
                to="/table/$schema/$table"
                params={{ schema: f.schema_name, table: f.table_name }}
                className="text-blue-600 hover:text-blue-800 hover:underline"
              >
                {f.schema_name}.{f.table_name}
              </Link>
              <p className="mt-1 text-sm text-gray-600">{f.description}</p>
            </div>
          ))}
          <a href="/findings?severity=error" className="text-sm text-blue-600 hover:underline">
            View all issues
          </a>
        </section>
      )}

      <section className="mb-6">
        <div className="flex justify-between items-center flex-wrap gap-2 mb-3">
          <h2 className="text-lg font-semibold text-gray-800">Findings</h2>
          <div className="flex flex-wrap gap-2">
            <input
              type="search"
              placeholder="Search findings..."
              className="min-w-[180px] px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400 transition-colors"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <select className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400" value={checkFilter} onChange={(e) => setCheckFilter(e.target.value)}>
              <option value="">All checks</option>
              {checkTypes.map((ct) => (
                <option key={ct} value={ct}>{ct}</option>
              ))}
            </select>
            <select className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400" value={sevFilter} onChange={(e) => setSevFilter(e.target.value)}>
              <option value="">All severities</option>
              {severities.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <select className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400" value={schemaFilter} onChange={(e) => setSchemaFilter(e.target.value)}>
              <option value="">All schemas</option>
              {schemas.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <button
              className="px-4 py-1.5 bg-gray-900 text-white rounded-lg text-sm cursor-pointer hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={() => refresh.mutate()}
              disabled={refresh.isPending}
            >
              {refresh.isPending ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>
        <FindingsTable findings={filteredFindings} />
      </section>

      <p className="text-xs text-gray-500">
        Last check:{" "}
        {stats.last_check_time
          ? stats.last_check_time.slice(0, 16).replace("T", " ")
          : "\u2014"}
      </p>

      {dbt_findings.length > 0 && (
        <section className="mb-6 mt-6">
          <div className="flex justify-between items-center flex-wrap gap-2 mb-3">
            <h2 className="text-lg font-semibold text-gray-800">dbt Results</h2>
            <Link to="/dbt" className="text-sm text-blue-600 hover:underline">View all</Link>
          </div>
          <StatsRow>
            {dbt_stats.error_count > 0 && (
              <StatCard value={dbt_stats.error_count} label="Errors" variant="error" />
            )}
            {dbt_stats.warning_count > 0 && (
              <StatCard value={dbt_stats.warning_count} label="Warnings" variant="warning" />
            )}
          </StatsRow>
          <table className="w-full bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden mb-6">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Severity</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Type</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Node</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {dbt_findings.slice(0, 5).map((f, i) => (
                <tr key={i} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3"><Badge type={f.severity}>{f.severity}</Badge></td>
                  <td className="px-4 py-3 text-sm text-gray-700">{f.resource_type}</td>
                  <td className="px-4 py-3 text-sm text-gray-700">{f.unique_id.includes(".") ? f.unique_id.split(".").slice(1).join(".") : f.unique_id}</td>
                  <td className="px-4 py-3 text-sm text-gray-700">{f.description}</td>
                </tr>
              ))}
              {dbt_findings.length > 5 && (
                <tr>
                  <td colSpan={4} className="text-center text-gray-400 py-3">
                    <Link to="/dbt" className="text-blue-600 hover:underline">{dbt_findings.length - 5} more...</Link>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
