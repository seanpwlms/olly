import { Fragment, useState } from "react";
import { useConnection } from "../hooks/useConnection";
import { useContracts } from "../hooks/queries";
import { StatCard } from "./StatCard";
import { StatsRow } from "./StatsRow";
import { Badge } from "./Badge";
import { DataTable, type Column } from "./DataTable";
import { EmptyState } from "./EmptyState";
import { NotConfigured } from "./NotConfigured";
import { ErrorState } from "./ErrorState";
import { SkeletonStatCards, SkeletonTable } from "./Skeleton";
import type { ContractStatus } from "../types";

function ContractDetails({ contract }: { contract: ContractStatus }) {
  return (
    <>
      {contract.columns.length > 0 && (
        <div className="mb-3">
          <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
            Columns
          </h4>
          <div className="grid grid-cols-3 gap-1 text-xs">
            <span className="font-medium text-gray-500 dark:text-gray-400">Name</span>
            <span className="font-medium text-gray-500 dark:text-gray-400">Type</span>
            <span className="font-medium text-gray-500 dark:text-gray-400">Nullable</span>
            {contract.columns.map((col) => (
              <Fragment key={col.column_name}>
                <span className="text-gray-700 dark:text-gray-300">{col.column_name}</span>
                <span className="text-gray-500 dark:text-gray-400">{col.expected_type}</span>
                <span className="text-gray-500 dark:text-gray-400">{col.nullable ? "yes" : "no"}</span>
              </Fragment>
            ))}
          </div>
        </div>
      )}
      {contract.findings.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
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
        <p className="text-xs text-gray-500 dark:text-gray-400">No details available.</p>
      )}
    </>
  );
}

const contractColumns: Column<ContractStatus>[] = [
  { key: "table", header: "Table", render: (c) => `${c.schema_name}.${c.table_name}` },
  { key: "connection", header: "Connection", render: (c) => c.connection_name ?? "all" },
  { key: "strict", header: "Strict", render: (c) => (c.strict ? "Yes" : "No") },
  { key: "columns", header: "Columns", render: (c) => c.columns.length },
  { key: "status", header: "Status", render: (c) => <Badge type={c.status}>{c.status}</Badge> },
];

export function ContractsContent() {
  const { connection } = useConnection();
  const { data, isLoading, isError, refetch } = useContracts(connection);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");

  if (isError) return <ErrorState message="Failed to load contracts." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <><SkeletonStatCards count={3} /><SkeletonTable rows={5} cols={5} /></>;

  if (!data.configured) {
    return (
      <NotConfigured
        description="Contracts assert the schema your tables are supposed to have \u2014 column names, types, and nullability \u2014 and flag any drift away from it."
        snippet={'[contracts]\nmodule = "contracts.py"'}
      />
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
              placeholder="Search tables…"
              className="min-w-[180px] px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-accent-500/40 focus:border-accent-400 transition-colors"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select
              className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-accent-500/40 focus:border-accent-400"
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
          <DataTable
            data={filtered}
            columns={contractColumns}
            rowKey={(c) => `${c.schema_name}.${c.table_name}`}
            className=""
            expandedContent={(c) => <ContractDetails contract={c} />}
          />
        )}
      </section>

    </>
  );
}
