import { useState } from "react";
import { useConnection } from "../hooks/useConnection";
import { useContracts } from "../hooks/queries";
import { StatCard } from "./StatCard";
import { StatsRow } from "./StatsRow";
import { Badge } from "./Badge";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { SkeletonStatCards, SkeletonTable } from "./Skeleton";
import type { ContractStatus } from "../types";

function ContractRow({ contract }: { contract: ContractStatus }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <tr
        className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-900/50 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="px-4 py-3 text-sm">
          <span className="text-gray-400 mr-1">{expanded ? "\u25BC" : "\u25B6"}</span>
          {contract.schema_name}.{contract.table_name}
        </td>
        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
          {contract.connection_name ?? "all"}
        </td>
        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
          {contract.strict ? "Yes" : "No"}
        </td>
        <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
          {contract.columns.length}
        </td>
        <td className="px-4 py-3">
          <Badge type={contract.status}>{contract.status}</Badge>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-gray-100 dark:border-gray-800">
          <td colSpan={5} className="px-4 py-3 bg-gray-50 dark:bg-gray-900/30">
            {contract.columns.length > 0 && (
              <div className="mb-3">
                <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
                  Columns
                </h4>
                <div className="grid grid-cols-3 gap-1 text-xs">
                  <span className="font-medium text-gray-500 dark:text-gray-400">Name</span>
                  <span className="font-medium text-gray-500 dark:text-gray-400">Type</span>
                  <span className="font-medium text-gray-500 dark:text-gray-400">Nullable</span>
                  {contract.columns.map((col) => (
                    <>
                      <span key={`${col.column_name}-name`} className="text-gray-700 dark:text-gray-300">{col.column_name}</span>
                      <span key={`${col.column_name}-type`} className="text-gray-500 dark:text-gray-400">{col.expected_type}</span>
                      <span key={`${col.column_name}-null`} className="text-gray-500 dark:text-gray-400">{col.nullable ? "yes" : "no"}</span>
                    </>
                  ))}
                </div>
              </div>
            )}
            {contract.findings.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
                  Findings
                </h4>
                <ul className="space-y-1">
                  {contract.findings.map((f, i) => (
                    <li key={i} className="text-xs text-gray-600 dark:text-gray-400">
                      <Badge type={f.severity}>{f.severity}</Badge>
                      <span className="ml-2">{f.description}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {contract.columns.length === 0 && contract.findings.length === 0 && (
              <p className="text-xs text-gray-400">No details available.</p>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

export function ContractsContent() {
  const { connection } = useConnection();
  const { data, isLoading, isError, refetch } = useContracts(connection);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");

  if (isError) return <ErrorState message="Failed to load contracts." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <><SkeletonStatCards count={3} /><SkeletonTable rows={5} cols={5} /></>;

  if (!data.configured) {
    return (
      <EmptyState message="No contracts module configured. Add [contracts] module to olly.toml to get started." />
    );
  }

  let filtered = data.contracts;
  if (statusFilter) {
    filtered = filtered.filter((c) => c.status === statusFilter);
  }
  if (search) {
    const q = search.toLowerCase();
    filtered = filtered.filter(
      (c) =>
        c.table_name.toLowerCase().includes(q) ||
        c.schema_name.toLowerCase().includes(q),
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
            Contracts <span className="font-normal text-gray-500 dark:text-gray-400 text-sm">({filtered.length})</span>
          </h2>
          <div className="flex flex-wrap gap-2 items-center">
            <input
              type="search"
              placeholder="Search tables..."
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
          </div>
        </div>
        {filtered.length === 0 ? (
          <EmptyState message="No contracts match your filters." />
        ) : (
          <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Table</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Connection</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Strict</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Columns</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <ContractRow key={`${c.schema_name}.${c.table_name}`} contract={c} />
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
