import { Badge } from "./Badge";
import type { DbtFinding } from "../types";

interface DbtFindingsTableProps {
  findings: DbtFinding[];
  onShowSql?: (sql: string, nodeId: string) => void;
}

function shortNodeId(uniqueId: string): string {
  const idx = uniqueId.indexOf(".");
  return idx >= 0 ? uniqueId.slice(idx + 1) : uniqueId;
}

export function DbtFindingsTable({ findings, onShowSql }: DbtFindingsTableProps) {
  if (findings.length === 0) {
    return <p className="text-center text-gray-400 py-8">No dbt findings</p>;
  }
  return (
    <table className="w-full bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden mb-6">
      <thead>
        <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Severity</th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Type</th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Node</th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Status</th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Time</th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Description</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
        {findings.map((f, i) => (
          <tr key={i} className={`hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors border-l-4 ${f.severity === "error" ? "border-l-red-500" : f.severity === "warning" ? "border-l-amber-500" : "border-l-emerald-500"}`}>
            <td className="px-4 py-3">
              <Badge type={f.severity}>{f.severity}</Badge>
            </td>
            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{f.resource_type}</td>
            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{shortNodeId(f.unique_id)}</td>
            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{f.status}</td>
            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{f.execution_time.toFixed(1)}s</td>
            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
              {f.description}
              {typeof f.details.compiled_code === "string" && onShowSql && (
                <button
                  className="ml-2 px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded text-blue-600 dark:text-blue-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors cursor-pointer"
                  onClick={() =>
                    onShowSql(f.details.compiled_code as string, f.unique_id)
                  }
                >
                  View SQL
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
