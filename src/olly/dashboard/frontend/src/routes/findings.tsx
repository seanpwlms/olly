import { useNavigate, useSearch } from "@tanstack/react-router";
import { useConnection } from "../hooks/useConnection";
import { useFindings } from "../hooks/queries";
import { StatCard } from "../components/StatCard";
import { StatsRow } from "../components/StatsRow";
import { FindingsTable } from "../components/FindingsTable";
import { GroupedFindingsTable } from "../components/GroupedFindingsTable";
import { Pagination } from "../components/Pagination";
import { ErrorState } from "../components/ErrorState";
import { EmptyState } from "../components/EmptyState";
import { DbtContent } from "../components/DbtContent";
import { SkeletonStatCards, SkeletonTable } from "../components/Skeleton";
import { findingsRoute, type FindingsSearch } from "../routeTree";

const tabs = [
  { key: "quality", label: "Quality" },
  { key: "dbt", label: "dbt" },
] as const;

export function FindingsPage() {
  const { connection } = useConnection();
  const search = useSearch({ from: findingsRoute.id });
  const navigate = useNavigate({ from: findingsRoute.id });

  const activeTab = search.tab === "dbt" ? "dbt" : "quality";

  const setFilter = (updates: Partial<FindingsSearch>) => {
    void navigate({
      search: (prev) => ({
        ...prev,
        ...updates,
        page: "page" in updates ? updates.page : 1,
      }),
    });
  };

  const switchTab = (tab: string) => {
    void navigate({
      search: tab === "dbt" ? { tab: "dbt" } : {},
      replace: true,
    });
  };

  return (
    <>
      <div className="flex items-center gap-6 mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Findings</h1>
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => switchTab(tab.key)}
              className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                activeTab === tab.key
                  ? "bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900"
                  : "text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-800"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "dbt" ? (
        <DbtContent />
      ) : (
        <QualityContent
          connection={connection}
          search={search}
          setFilter={setFilter}
        />
      )}
    </>
  );
}

function QualityContent({
  connection,
  search,
  setFilter,
}: {
  connection: string;
  search: FindingsSearch;
  setFilter: (updates: Partial<FindingsSearch>) => void;
}) {
  const checkType = search.check_type ?? "";
  const severity = search.severity ?? "";
  const schema = search.schema ?? "";
  const q = search.q ?? "";
  const page = search.page ?? 1;
  const view = search.view === "flat" ? "flat" : "grouped";

  const { data, isLoading, isError, refetch } = useFindings({
    connection,
    check_type: checkType,
    severity,
    schema,
    q,
    page,
  });

  if (isError) return <ErrorState message="Failed to load findings." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <><SkeletonStatCards count={3} /><SkeletonTable rows={5} cols={5} /></>;

  const { findings, stats, filters, total_pages, total, last_check_time } = data;

  const hasFilters = !!(checkType || severity || schema || q);
  const isHealthy = stats.error_count === 0 && stats.warning_count === 0 && !hasFilters;

  return (
    <>
      {isHealthy ? (
        <div className="mb-6">
          <EmptyState variant="healthy" message="No issues detected — all checks passed" />
          {last_check_time && (
            <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-2">
              Last check: {last_check_time.slice(0, 16).replace("T", " ")}
            </p>
          )}
        </div>
      ) : (
        <StatsRow>
          <StatCard value={stats.total_count} label="Total Findings" />
          <StatCard value={stats.error_count} label="Errors" variant="error" />
          <StatCard value={stats.warning_count} label="Warnings" variant="warning" />
        </StatsRow>
      )}

      <section className="mb-6">
        <div className="flex justify-between items-center flex-wrap gap-2 mb-3">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
            All Findings <span className="font-normal text-gray-500 dark:text-gray-400 text-sm">({total})</span>
          </h2>
          <div className="flex flex-wrap gap-2 items-center">
            <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              <button
                onClick={() => setFilter({ view: "grouped" })}
                className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
                  view === "grouped"
                    ? "bg-gray-900 text-white"
                    : "bg-white dark:bg-gray-900 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                }`}
              >
                Grouped
              </button>
              <button
                onClick={() => setFilter({ view: "flat" })}
                className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
                  view === "flat"
                    ? "bg-gray-900 text-white"
                    : "bg-white dark:bg-gray-900 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                }`}
              >
                Flat
              </button>
            </div>
            <input
              type="search"
              placeholder="Search findings..."
              className="min-w-[180px] px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400 transition-colors"
              value={q}
              onChange={(e) => setFilter({ q: e.target.value || undefined })}
            />
            <select
              className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              value={severity}
              onChange={(e) => setFilter({ severity: e.target.value || undefined })}
            >
              <option value="">All severities</option>
              {filters.severities.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select
              className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              value={schema}
              onChange={(e) => setFilter({ schema: e.target.value || undefined })}
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
        {Object.keys(stats.by_check_type).length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {Object.entries(stats.by_check_type).map(([ct, [errors, warnings]]) => {
              const isActive = checkType === ct;
              return (
                <button
                  key={ct}
                  onClick={() => setFilter({ check_type: isActive ? undefined : ct })}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                    isActive
                      ? "bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900"
                      : "bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                  }`}
                >
                  {ct}
                  {errors > 0 && <span className={isActive ? "text-red-300 dark:text-red-700" : "text-red-600 dark:text-red-400"}>{errors}</span>}
                  {warnings > 0 && <span className={isActive ? "text-amber-300 dark:text-amber-700" : "text-amber-600 dark:text-amber-400"}>{warnings}</span>}
                </button>
              );
            })}
          </div>
        )}
        {findings.length === 0 ? (
          hasFilters ? (
            <EmptyState message="No findings match your filters." />
          ) : null
        ) : view === "grouped" ? (
          <GroupedFindingsTable findings={findings} />
        ) : (
          <FindingsTable findings={findings} />
        )}
        {findings.length > 0 && (
          <Pagination page={page} totalPages={total_pages} onPageChange={(p) => setFilter({ page: p > 1 ? p : undefined })} />
        )}
      </section>

      {last_check_time && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Last check: {last_check_time.slice(0, 16).replace("T", " ")}
        </p>
      )}
    </>
  );
}
