import { useEffect, useState } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useConnection } from "../hooks/useConnection";
import { useFindings } from "../hooks/queries";
import { FindingsTable } from "../components/FindingsTable";
import { GroupedFindingsTable } from "../components/GroupedFindingsTable";
import { Pagination } from "../components/Pagination";
import { ErrorState } from "../components/ErrorState";
import { EmptyState } from "../components/EmptyState";
import { SkeletonTable } from "../components/Skeleton";
import { SelectionBar } from "../components/SelectionBar";
import { FilterPopover, FilterSelect } from "../components/FilterPopover";
import { ActiveFilters, type ActiveFilter } from "../components/ActiveFilters";
import { findingsRoute, type FindingsSearch } from "../routeTree";
import type { FindingsStats } from "../types";

const humanize = (v: string) => v.replace(/_/g, " ");

/** One-line totals in place of a row of stat cards; zero counts are left out. */
function FindingsSummary({ stats }: { stats: FindingsStats }) {
  const parts: { text: string; className?: string }[] = [
    { text: `${stats.total_count} finding${stats.total_count === 1 ? "" : "s"}`, className: "font-medium text-gray-900 dark:text-gray-100" },
  ];
  if (stats.error_count > 0)
    parts.push({ text: `${stats.error_count} error${stats.error_count === 1 ? "" : "s"}`, className: "text-red-600 dark:text-red-400" });
  if (stats.warning_count > 0)
    parts.push({ text: `${stats.warning_count} warning${stats.warning_count === 1 ? "" : "s"}`, className: "text-amber-700 dark:text-amber-400" });
  if (stats.in_progress_count > 0) parts.push({ text: `${stats.in_progress_count} in progress` });
  if (stats.completed_count > 0) parts.push({ text: `${stats.completed_count} completed` });

  return (
    <p className="mb-5 text-sm text-gray-600 dark:text-gray-400">
      {parts.map((p, i) => (
        <span key={p.text}>
          {i > 0 && <span className="mx-2 text-gray-300 dark:text-gray-600" aria-hidden="true">·</span>}
          <span className={p.className}>{p.text}</span>
        </span>
      ))}
    </p>
  );
}

export function FindingsPage() {
  const { connection } = useConnection();
  const search = useSearch({ from: findingsRoute.id });
  const navigate = useNavigate({ from: findingsRoute.id });

  const setFilter = (updates: Partial<FindingsSearch>) => {
    void navigate({
      search: (prev) => ({
        ...prev,
        ...updates,
        page: "page" in updates ? updates.page : 1,
      }),
    });
  };

  return (
    <>
      <h1 className="text-2xl font-semibold text-gray-900 dark:text-white mb-6">Findings</h1>
      <QualityContent
        connection={connection}
        search={search}
        setFilter={setFilter}
      />
    </>
  );
}

function ViewToggle({
  view,
  onChange,
}: {
  view: "grouped" | "flat";
  onChange: (view: "grouped" | "flat") => void;
}) {
  return (
    <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      {(["grouped", "flat"] as const).map((v) => (
        <button
          key={v}
          onClick={() => onChange(v)}
          className={`px-2.5 py-1.5 text-xs font-medium capitalize transition-colors cursor-pointer ${
            view === v
              ? "bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900"
              : "bg-white dark:bg-gray-900 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
          }`}
        >
          {v}
        </button>
      ))}
    </div>
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
  const disposition = search.disposition ?? "";
  const q = search.q ?? "";
  const page = search.page ?? 1;
  const view = search.view === "flat" ? "flat" : "grouped";

  const { data, isLoading, isError, refetch } = useFindings({
    connection,
    check_type: checkType,
    severity,
    schema,
    disposition,
    q,
    page,
  });

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const filterKey = [connection, checkType, severity, schema, disposition, q].join("|");
  // Changing filters changes what "all matching" means, so start over.
  useEffect(() => setSelected(new Set()), [filterKey]);

  const pageIds = (data?.findings ?? [])
    .map((f) => f.id)
    .filter((id): id is number => id !== null);

  if (isError) return <ErrorState message="Failed to load findings." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <SkeletonTable rows={8} cols={5} />;

  const { findings, stats, filters, total_pages, total, all_ids } = data;

  // Every filter except the check-type chips, which have their own affordance.
  const popoverCount = [severity, schema, disposition].filter(Boolean).length;

  const activeFilters: ActiveFilter[] = [
    checkType && { label: "check", value: checkType, onRemove: () => setFilter({ check_type: undefined }) },
    severity && { label: "severity", value: severity, onRemove: () => setFilter({ severity: undefined }) },
    schema && { label: "schema", value: schema, onRemove: () => setFilter({ schema: undefined }) },
    disposition && { label: "status", value: humanize(disposition), onRemove: () => setFilter({ disposition: undefined }) },
    q && { label: "search", value: q, onRemove: () => setFilter({ q: undefined }) },
  ].filter(Boolean) as ActiveFilter[];

  const hasFilters = activeFilters.length > 0;
  const isHealthy = stats.error_count === 0 && stats.warning_count === 0 && !hasFilters;

  const clearAll = () =>
    setFilter({
      check_type: undefined,
      severity: undefined,
      schema: undefined,
      disposition: undefined,
      q: undefined,
    });

  return (
    <>
      {isHealthy ? (
        <div className="mb-6">
          <EmptyState variant="healthy" message="No findings. All checks passed." />
        </div>
      ) : (
        <FindingsSummary stats={stats} />
      )}

      <section className="mb-6">
        <div className="flex justify-between items-center flex-wrap gap-2 mb-3">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {hasFilters && `${total} matching`}
          </span>
          <div className="flex flex-wrap gap-2 items-center">
            <ViewToggle view={view} onChange={(v) => setFilter({ view: v })} />
            <input
              type="search"
              placeholder="Search findings…"
              className="min-w-[180px] px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-accent-500/40 focus:border-accent-400 transition-colors"
              value={q}
              onChange={(e) => setFilter({ q: e.target.value || undefined })}
            />
            <FilterPopover activeCount={popoverCount}>
              <FilterSelect
                label="Severity"
                value={severity}
                options={filters.severities}
                allLabel="All severities"
                onChange={(v) => setFilter({ severity: v || undefined })}
              />
              <FilterSelect
                label="Schema"
                value={schema}
                options={filters.schemas}
                allLabel="All schemas"
                onChange={(v) => setFilter({ schema: v || undefined })}
              />
              <FilterSelect
                label="Status"
                value={disposition}
                options={filters.dispositions ?? []}
                allLabel="All statuses"
                format={humanize}
                onChange={(v) => setFilter({ disposition: v || undefined })}
              />
            </FilterPopover>
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
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors cursor-pointer ${
                    isActive
                      ? "bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900"
                      : "bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                  }`}
                >
                  {ct}
                  {errors > 0 && <span className={isActive ? "text-red-300 dark:text-red-700" : "text-red-600 dark:text-red-400"}>{errors}</span>}
                  {warnings > 0 && <span className={isActive ? "text-amber-300 dark:text-amber-700" : "text-amber-700 dark:text-amber-400"}>{warnings}</span>}
                </button>
              );
            })}
          </div>
        )}

        <ActiveFilters filters={activeFilters} onClearAll={clearAll} />

        {findings.length === 0 ? (
          <EmptyState
            message={
              hasFilters
                ? "No findings match your filters."
                : "No findings to show."
            }
          />
        ) : (
          <>
            <SelectionBar
              pageIds={pageIds}
              allIds={all_ids}
              selected={selected}
              onChange={setSelected}
            />
            {view === "grouped" ? (
              <GroupedFindingsTable
                findings={findings}
                selected={selected}
                onSelectionChange={setSelected}
              />
            ) : (
              <FindingsTable
                findings={findings}
                selected={selected}
                onSelectionChange={setSelected}
              />
            )}
          </>
        )}
        {findings.length > 0 && (
          <Pagination page={page} totalPages={total_pages} onPageChange={(p) => setFilter({ page: p > 1 ? p : undefined })} />
        )}
      </section>
    </>
  );
}
