import { useState } from "react";
import { useConnection } from "../hooks/useConnection";
import { useFindings } from "../hooks/queries";
import { StatCard } from "../components/StatCard";
import { StatsRow } from "../components/StatsRow";
import { FindingsTable } from "../components/FindingsTable";
import { Pagination } from "../components/Pagination";

export function FindingsPage() {
  const { connection } = useConnection();
  const [checkType, setCheckType] = useState("");
  const [severity, setSeverity] = useState("");
  const [schema, setSchema] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading } = useFindings({
    connection,
    check_type: checkType,
    severity,
    schema,
    q,
    page,
  });

  if (isLoading || !data) return <div className="text-center text-gray-500 py-8">Loading...</div>;

  const { findings, stats, filters, total_pages, total, last_check_time } = data;

  return (
    <>
      <h1 className="text-2xl font-bold text-gray-900 mb-4">Findings</h1>

      <StatsRow>
        <StatCard value={stats.total_count} label="Total Findings" />
        <StatCard value={stats.error_count} label="Errors" variant="error" />
        <StatCard value={stats.warning_count} label="Warnings" variant="warning" />
      </StatsRow>

      {Object.keys(stats.by_check_type).length > 0 && (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">By Check Type</h2>
          <StatsRow>
            {Object.entries(stats.by_check_type).map(([ct, [errors, warnings]]) => (
              <div key={ct} className="bg-white rounded-lg border border-gray-200 shadow-sm px-5 py-4 flex-1 min-w-[140px]">
                <div className="text-xs text-gray-500 uppercase tracking-wide">{ct}</div>
                <div className="flex gap-2 mt-1.5">
                  {errors > 0 && (
                    <span className="text-sm font-semibold text-red-600">
                      {errors} error{errors !== 1 ? "s" : ""}
                    </span>
                  )}
                  {warnings > 0 && (
                    <span className="text-sm font-semibold text-amber-600">
                      {warnings} warning{warnings !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </StatsRow>
        </section>
      )}

      <section className="mb-6">
        <div className="flex justify-between items-center flex-wrap gap-2 mb-3">
          <h2 className="text-lg font-semibold text-gray-800">
            All Findings <span className="font-normal text-gray-500 text-sm">({total})</span>
          </h2>
          <div className="flex flex-wrap gap-2">
            <input
              type="search"
              placeholder="Search findings..."
              className="min-w-[180px] px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400 transition-colors"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
            <select
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              value={checkType}
              onChange={(e) => {
                setCheckType(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All checks</option>
              {filters.check_types.map((ct) => (
                <option key={ct} value={ct}>
                  {ct}
                </option>
              ))}
            </select>
            <select
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              value={severity}
              onChange={(e) => {
                setSeverity(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All severities</option>
              {filters.severities.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              value={schema}
              onChange={(e) => {
                setSchema(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All schemas</option>
              {filters.schemas.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>
        <FindingsTable findings={findings} />
        <Pagination page={page} totalPages={total_pages} onPageChange={setPage} />
      </section>

      {last_check_time && (
        <p className="text-xs text-gray-500">
          Last check: {last_check_time.slice(0, 16).replace("T", " ")}
        </p>
      )}
    </>
  );
}
