import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { Badge } from "./Badge";
import { DispositionSelect } from "./DispositionSelect";
import { DispositionHistory } from "./DispositionHistory";
import { FindingDetails } from "./FindingDetails";
import { BulkActionBar } from "./BulkActionBar";
import { timeAgo } from "../utils/timeAgo";
import type { Finding } from "../types";

interface FindingsTableProps {
  findings: Finding[];
  showLink?: boolean;
}

function getBorderClass(f: Finding): string {
  if (f.disposition === "completed") return "border-l-emerald-400 dark:border-l-emerald-600";
  if (f.disposition === "no_action") return "border-l-gray-300 dark:border-l-gray-600";
  if (f.severity === "error") return "border-l-red-500";
  if (f.severity === "warning") return "border-l-amber-500";
  return "border-l-emerald-500";
}

function getRowOpacity(disposition: string): string {
  if (disposition === "completed") return "opacity-50";
  if (disposition === "no_action") return "opacity-60";
  return "";
}

export function FindingsTable({ findings, showLink = true }: FindingsTableProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  if (findings.length === 0) {
    return <p className="text-center text-gray-400 py-8">No findings</p>;
  }

  const selectableIds = findings.map((f) => f.id).filter((id): id is number => id !== null);
  const allSelected = selectableIds.length > 0 && selectableIds.every((id) => selectedIds.has(id));

  const toggleAll = () => {
    setSelectedIds(allSelected ? new Set() : new Set(selectableIds));
  };

  const toggleOne = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <>
      <BulkActionBar selectedIds={selectedIds} onClear={() => setSelectedIds(new Set())} />
      <table className="w-full bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden mb-6">
        <thead>
          <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
            <th className="px-2 py-3 w-8">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                className="rounded border-gray-300 dark:border-gray-600"
              />
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Check</th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Severity</th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Table</th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Description</th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">When</th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
          {findings.map((f, i) => (
            <>
              <tr
                key={f.id ?? i}
                className={`hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors border-l-4 cursor-pointer ${getBorderClass(f)} ${getRowOpacity(f.disposition)}`}
                onClick={() => setExpandedId(expandedId === f.id ? null : f.id)}
              >
                <td className="px-2 py-3 w-8" onClick={(e) => e.stopPropagation()}>
                  {f.id !== null && (
                    <input
                      type="checkbox"
                      checked={selectedIds.has(f.id)}
                      onChange={() => toggleOne(f.id!)}
                      className="rounded border-gray-300 dark:border-gray-600"
                    />
                  )}
                </td>
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
                      onClick={(e) => e.stopPropagation()}
                    >
                      {f.schema_name}.{f.table_name}
                    </Link>
                  ) : (
                    <span className="text-gray-700 dark:text-gray-300">{f.schema_name}.{f.table_name}</span>
                  )}
                </td>
                <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{f.description}</td>
                <td className="px-4 py-3 text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">{timeAgo(f.created_at)}</td>
                <td className="px-4 py-3">
                  <DispositionSelect findingId={f.id} currentDisposition={f.disposition} />
                </td>
              </tr>
              {expandedId === f.id && f.id !== null && (
                <tr key={`history-${f.id}`}>
                  <td colSpan={7} className="px-8 py-2 bg-gray-50 dark:bg-gray-800/50">
                    <FindingDetails finding={f} />
                    <DispositionHistory findingId={f.id} />
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </>
  );
}
