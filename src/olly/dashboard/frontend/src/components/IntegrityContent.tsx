import { useState } from "react";
import { useConnection } from "../hooks/useConnection";
import { useIntegrity } from "../hooks/queries";
import { StatCard } from "./StatCard";
import { StatsRow } from "./StatsRow";
import { Badge } from "./Badge";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { SkeletonStatCards, SkeletonTable } from "./Skeleton";
import type { SyncStatus } from "../types";

function SyncRow({ sync }: { sync: SyncStatus }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <tr
        className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-900/50 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="px-4 py-3 text-sm">
          <span className="text-gray-400 mr-1">{expanded ? "\u25BC" : "\u25B6"}</span>
          {sync.name}
        </td>
        <td className="px-4 py-3">
          <Badge type={sync.method}>{sync.method}</Badge>
        </td>
        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
          {sync.source_table} <span className="text-gray-300 dark:text-gray-600 mx-1">&rarr;</span> {sync.target_table}
        </td>
        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
          {sync.key ?? "-"}
        </td>
        <td className="px-4 py-3">
          <Badge type={sync.status}>{sync.status}</Badge>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-gray-100 dark:border-gray-800">
          <td colSpan={5} className="px-4 py-3 bg-gray-50 dark:bg-gray-900/30">
            <div className="grid grid-cols-2 gap-2 text-xs mb-2">
              <div>
                <span className="font-medium text-gray-500 dark:text-gray-400">Source: </span>
                <span className="text-gray-700 dark:text-gray-300">{sync.source} / {sync.source_table}</span>
              </div>
              <div>
                <span className="font-medium text-gray-500 dark:text-gray-400">Target: </span>
                <span className="text-gray-700 dark:text-gray-300">{sync.target} / {sync.target_table}</span>
              </div>
              <div>
                <span className="font-medium text-gray-500 dark:text-gray-400">Method: </span>
                <span className="text-gray-700 dark:text-gray-300">{sync.method}</span>
              </div>
              <div>
                <span className="font-medium text-gray-500 dark:text-gray-400">Severity: </span>
                <Badge type={sync.severity}>{sync.severity}</Badge>
              </div>
            </div>
            {sync.findings.length > 0 ? (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
                  Findings
                </h4>
                <ul className="space-y-1">
                  {sync.findings.map((f, i) => (
                    <li key={i} className="text-xs text-gray-600 dark:text-gray-400">
                      <Badge type={f.severity}>{f.severity}</Badge>
                      <span className="ml-2">{f.description}</span>
                      {f.details.source_value !== undefined && (
                        <span className="ml-2 text-gray-400">
                          (source: {String(f.details.source_value)}, target: {String(f.details.target_value)})
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-xs text-gray-400">No issues detected.</p>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

export function IntegrityContent() {
  const { connection } = useConnection();
  const { data, isLoading, isError, refetch } = useIntegrity(connection);
  const [statusFilter, setStatusFilter] = useState("");
  const [methodFilter, setMethodFilter] = useState("");
  const [search, setSearch] = useState("");

  if (isError) return <ErrorState message="Failed to load integrity syncs." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <><SkeletonStatCards count={3} /><SkeletonTable rows={5} cols={5} /></>;

  if (!data.configured) {
    return (
      <EmptyState message="No integrity module configured. Add [integrity] module to olly.toml to get started." />
    );
  }

  const methods = [...new Set(data.syncs.map((s) => s.method))].sort();

  let filtered = data.syncs;
  if (statusFilter) {
    filtered = filtered.filter((s) => s.status === statusFilter);
  }
  if (methodFilter) {
    filtered = filtered.filter((s) => s.method === methodFilter);
  }
  if (search) {
    const q = search.toLowerCase();
    filtered = filtered.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.source_table.toLowerCase().includes(q) ||
        s.target_table.toLowerCase().includes(q),
    );
  }

  return (
    <>
      <StatsRow>
        <StatCard value={data.pass_count} label="Passing" variant="ok" />
        <StatCard value={data.fail_count} label="Failing" variant="error" />
        <StatCard value={data.total_count} label="Total" />
      </StatsRow>

      <section>
        <div className="flex justify-between items-center flex-wrap gap-2 mb-3">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
            Integrity Syncs <span className="font-normal text-gray-500 dark:text-gray-400 text-sm">({filtered.length})</span>
          </h2>
          <div className="flex flex-wrap gap-2 items-center">
            <input
              type="search"
              placeholder="Search syncs..."
              className="min-w-[180px] px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400 transition-colors"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select
              className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">All statuses</option>
              <option value="pass">Pass</option>
              <option value="fail">Fail</option>
            </select>
            <select
              className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              value={methodFilter}
              onChange={(e) => setMethodFilter(e.target.value)}
            >
              <option value="">All methods</option>
              {methods.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
        </div>
        {filtered.length === 0 ? (
          <EmptyState message="No syncs match your filters." />
        ) : (
          <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Sync Name</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Method</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Source &rarr; Target</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Key</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <SyncRow key={s.name} sync={s} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {data.last_check_time && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-4">
          Last check: {data.last_check_time.slice(0, 16).replace("T", " ")}
        </p>
      )}
    </>
  );
}
