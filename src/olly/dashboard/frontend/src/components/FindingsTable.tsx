import { Link } from "@tanstack/react-router";
import { Badge } from "./Badge";
import type { Finding } from "../types";

interface FindingsTableProps {
  findings: Finding[];
  showLink?: boolean;
}

export function FindingsTable({ findings, showLink = true }: FindingsTableProps) {
  if (findings.length === 0) {
    return <p className="text-center text-gray-400 py-8">No findings</p>;
  }
  return (
    <table className="w-full bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden mb-6">
      <thead>
        <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Check</th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Severity</th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Table</th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Description</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
        {findings.map((f, i) => (
          <tr key={i} className={`hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors border-l-4 ${f.severity === "error" ? "border-l-red-500" : f.severity === "warning" ? "border-l-amber-500" : "border-l-emerald-500"}`}>
            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{f.check_type}</td>
            <td className="px-4 py-3">
              <Badge type={f.severity}>{f.severity}</Badge>
            </td>
            <td className="px-4 py-3 text-sm">
              {showLink ? (
                <Link
                  to="/table/$schema/$table"
                  params={{
                    schema: f.schema_name,
                    table: f.table_name,
                  }}
                  className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
                >
                  {f.schema_name}.{f.table_name}
                </Link>
              ) : (
                <span className="text-gray-700 dark:text-gray-300">{f.schema_name}.{f.table_name}</span>
              )}
            </td>
            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{f.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
