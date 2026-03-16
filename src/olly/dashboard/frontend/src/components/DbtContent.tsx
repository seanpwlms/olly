import { useState } from "react";
import { useConnection } from "../hooks/useConnection";
import { useDbt } from "../hooks/queries";
import { StatCard } from "./StatCard";
import { StatsRow } from "./StatsRow";
import { DbtFindingsTable } from "./DbtFindingsTable";
import { DbtExecutionLeaderboard } from "./DbtExecutionLeaderboard";
import { DbtRunTrendChart } from "./DbtRunTrendChart";
import { CompiledSqlModal } from "./CompiledSqlModal";
import { Pagination } from "./Pagination";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { SkeletonStatCards, SkeletonTable } from "./Skeleton";
import type { DbtFinding } from "../types";

const PAGE_SIZE = 50;

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s.toFixed(0)}s`;
}

const tabs = [
  { key: "overview", label: "Overview" },
  { key: "nodes", label: "All Nodes" },
] as const;

type TabKey = (typeof tabs)[number]["key"];

export function DbtContent() {
  const { connection } = useConnection();
  const { data, isLoading, isError, refetch } = useDbt(connection);

  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [rtFilter, setRtFilter] = useState("");
  const [sevFilter, setSevFilter] = useState("");
  const [allRtFilter, setAllRtFilter] = useState("");
  const [allSearch, setAllSearch] = useState("");
  const [allPage, setAllPage] = useState(1);
  const [sqlModal, setSqlModal] = useState<{
    sql: string;
    nodeId: string;
    dbtRunId: number | null;
  } | null>(null);

  if (isError) return <ErrorState message="Failed to load dbt results." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <><SkeletonStatCards count={5} /><SkeletonTable rows={5} cols={4} /></>;

  const { dbt_stats, dbt_findings, resource_types, severities, execution_leaderboard, run_history } = data;

  const onShowSql = (sql: string, nodeId: string, dbtRunId: number | null) =>
    setSqlModal({ sql, nodeId, dbtRunId });

  return (
    <>
      <div className="flex items-center gap-6 mb-6">
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
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

      {activeTab === "overview" ? (
        <OverviewTab
          dbt_stats={dbt_stats}
          dbt_findings={dbt_findings}
          resource_types={resource_types}
          severities={severities}
          execution_leaderboard={execution_leaderboard}
          run_history={run_history}
          rtFilter={rtFilter}
          setRtFilter={setRtFilter}
          sevFilter={sevFilter}
          setSevFilter={setSevFilter}
          onShowSql={onShowSql}
        />
      ) : (
        <AllNodesTab
          dbt_findings={dbt_findings}
          resource_types={resource_types}
          allRtFilter={allRtFilter}
          setAllRtFilter={setAllRtFilter}
          allSearch={allSearch}
          setAllSearch={setAllSearch}
          page={allPage}
          setPage={setAllPage}
          onShowSql={onShowSql}
        />
      )}

      {sqlModal && (
        <CompiledSqlModal
          sql={sqlModal.sql}
          nodeId={sqlModal.nodeId}
          dbtRunId={sqlModal.dbtRunId}
          onClose={() => setSqlModal(null)}
        />
      )}
    </>
  );
}

function OverviewTab({
  dbt_stats,
  dbt_findings,
  resource_types,
  severities,
  execution_leaderboard,
  run_history,
  rtFilter,
  setRtFilter,
  sevFilter,
  setSevFilter,
  onShowSql,
}: {
  dbt_stats: { error_count: number; warning_count: number; pass_count: number; total_count: number; total_execution_time: number };
  dbt_findings: DbtFinding[];
  resource_types: string[];
  severities: string[];
  execution_leaderboard: { unique_id: string; resource_type: string; execution_time: number; status: string; severity: string }[];
  run_history: { created_at: string; elapsed_time: number; total_nodes: number; error_count: number; warning_count: number; pass_count: number }[];
  rtFilter: string;
  setRtFilter: (v: string) => void;
  sevFilter: string;
  setSevFilter: (v: string) => void;
  onShowSql: (sql: string, nodeId: string, dbtRunId: number | null) => void;
}) {
  let issueFindings = dbt_findings.filter((f) => f.severity !== "pass");
  if (rtFilter) issueFindings = issueFindings.filter((f) => f.resource_type === rtFilter);
  if (sevFilter) issueFindings = issueFindings.filter((f) => f.severity === sevFilter);

  return (
    <>
      <StatsRow>
        <StatCard value={dbt_stats.error_count} label="Errors" variant="error" />
        <StatCard value={dbt_stats.warning_count} label="Warnings" variant="warning" />
        <StatCard value={dbt_stats.pass_count} label="Passed" variant="ok" />
        <StatCard value={dbt_stats.total_count} label="Total" />
        <StatCard value={formatDuration(dbt_stats.total_execution_time)} label="Total Time" />
      </StatsRow>

      {run_history.length >= 2 && <DbtRunTrendChart data={run_history} />}

      {execution_leaderboard.length > 0 && (
        <DbtExecutionLeaderboard entries={execution_leaderboard} />
      )}

      <section className="mb-6">
        <div className="flex justify-between items-center flex-wrap gap-2 mb-3">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">Issues</h2>
          <div className="flex flex-wrap gap-2">
            <select
              className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              value={rtFilter}
              onChange={(e) => setRtFilter(e.target.value)}
            >
              <option value="">All types</option>
              {resource_types.map((rt) => <option key={rt} value={rt}>{rt}</option>)}
            </select>
            <select
              className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              value={sevFilter}
              onChange={(e) => setSevFilter(e.target.value)}
            >
              <option value="">All severities</option>
              {severities.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>
        {issueFindings.length > 0 ? (
          <DbtFindingsTable findings={issueFindings} onShowSql={onShowSql} />
        ) : dbt_stats.total_count > 0 ? (
          <EmptyState message={`All ${dbt_stats.total_count} dbt nodes passed.`} />
        ) : (
          <EmptyState message="No dbt findings" />
        )}
      </section>
    </>
  );
}

function AllNodesTab({
  dbt_findings,
  resource_types,
  allRtFilter,
  setAllRtFilter,
  allSearch,
  setAllSearch,
  page,
  setPage,
  onShowSql,
}: {
  dbt_findings: DbtFinding[];
  resource_types: string[];
  allRtFilter: string;
  setAllRtFilter: (v: string) => void;
  allSearch: string;
  setAllSearch: (v: string) => void;
  page: number;
  setPage: (p: number) => void;
  onShowSql: (sql: string, nodeId: string, dbtRunId: number | null) => void;
}) {
  let filtered = dbt_findings;
  if (allRtFilter) filtered = filtered.filter((f) => f.resource_type === allRtFilter);
  if (allSearch) {
    const q = allSearch.toLowerCase();
    filtered = filtered.filter(
      (f) => f.unique_id.toLowerCase().includes(q) || f.description.toLowerCase().includes(q),
    );
  }

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageItems = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  return (
    <section className="mb-6">
      <div className="flex justify-between items-center flex-wrap gap-2 mb-3">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
          All Nodes{" "}
          <span className="font-normal text-gray-500 dark:text-gray-400 text-sm">({total})</span>
        </h2>
        <div className="flex flex-wrap gap-2">
          <input
            type="search"
            placeholder="Search nodes..."
            className="min-w-[180px] px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400 transition-colors"
            value={allSearch}
            onChange={(e) => { setAllSearch(e.target.value); setPage(1); }}
          />
          <select
            className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
            value={allRtFilter}
            onChange={(e) => { setAllRtFilter(e.target.value); setPage(1); }}
          >
            <option value="">All types</option>
            {resource_types.map((rt) => <option key={rt} value={rt}>{rt}</option>)}
          </select>
        </div>
      </div>
      {pageItems.length > 0 ? (
        <>
          <DbtFindingsTable findings={pageItems} onShowSql={onShowSql} compact />
          <Pagination page={safePage} totalPages={totalPages} onPageChange={setPage} />
        </>
      ) : (
        <EmptyState message="No nodes match your filters." />
      )}
    </section>
  );
}
