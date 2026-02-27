import { useState } from "react";
import { useConnection } from "../hooks/useConnection";
import { useDbt } from "../hooks/queries";
import { StatCard } from "../components/StatCard";
import { StatsRow } from "../components/StatsRow";
import { DbtFindingsTable } from "../components/DbtFindingsTable";
import { CompiledSqlModal } from "../components/CompiledSqlModal";
import { EmptyState } from "../components/EmptyState";

export function DbtPage() {
  const { connection } = useConnection();
  const { data, isLoading } = useDbt(connection);
  const [rtFilter, setRtFilter] = useState("");
  const [sevFilter, setSevFilter] = useState("");
  const [sqlModal, setSqlModal] = useState<{
    sql: string;
    nodeId: string;
  } | null>(null);

  if (isLoading || !data) return <div className="text-center text-gray-500 py-8">Loading...</div>;

  const { dbt_stats, dbt_findings, resource_types, severities } = data;

  let issueFindings = dbt_findings.filter((f) => f.severity !== "pass");
  if (rtFilter) issueFindings = issueFindings.filter((f) => f.resource_type === rtFilter);
  if (sevFilter) issueFindings = issueFindings.filter((f) => f.severity === sevFilter);

  return (
    <>
      <h1 className="text-2xl font-bold text-gray-900 mb-4">dbt Run Results</h1>

      <StatsRow>
        <StatCard value={dbt_stats.error_count} label="Errors" variant="error" />
        <StatCard value={dbt_stats.warning_count} label="Warnings" variant="warning" />
        <StatCard value={dbt_stats.pass_count} label="Passed" variant="ok" />
        <StatCard value={dbt_stats.total_count} label="Total" />
      </StatsRow>

      <section className="mb-6">
        <div className="flex justify-between items-center flex-wrap gap-2 mb-3">
          <h2 className="text-lg font-semibold text-gray-800">Issues</h2>
          <div className="flex flex-wrap gap-2">
            <select
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              value={rtFilter}
              onChange={(e) => setRtFilter(e.target.value)}
            >
              <option value="">All types</option>
              {resource_types.map((rt) => (
                <option key={rt} value={rt}>
                  {rt}
                </option>
              ))}
            </select>
            <select
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              value={sevFilter}
              onChange={(e) => setSevFilter(e.target.value)}
            >
              <option value="">All severities</option>
              {severities.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>
        {issueFindings.length > 0 ? (
          <DbtFindingsTable
            findings={issueFindings}
            onShowSql={(sql, nodeId) => setSqlModal({ sql, nodeId })}
          />
        ) : dbt_stats.total_count > 0 ? (
          <EmptyState
            message={`All ${dbt_stats.total_count} dbt nodes passed.`}
          />
        ) : (
          <EmptyState message="No dbt findings" />
        )}
      </section>

      {sqlModal && (
        <CompiledSqlModal
          sql={sqlModal.sql}
          nodeId={sqlModal.nodeId}
          onClose={() => setSqlModal(null)}
        />
      )}
    </>
  );
}
