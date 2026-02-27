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
    <table className="w-full bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden mb-6">
      <thead>
        <tr className="bg-gray-50 border-b border-gray-200">
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Check</th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Severity</th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Table</th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Description</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100">
        {findings.map((f, i) => (
          <tr key={i} className="hover:bg-gray-50 transition-colors">
            <td className="px-4 py-3 text-sm text-gray-700">{f.check_type}</td>
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
                  className="text-blue-600 hover:text-blue-800 hover:underline"
                >
                  {f.schema_name}.{f.table_name}
                </Link>
              ) : (
                <span className="text-gray-700">{f.schema_name}.{f.table_name}</span>
              )}
            </td>
            <td className="px-4 py-3 text-sm text-gray-700">{f.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
