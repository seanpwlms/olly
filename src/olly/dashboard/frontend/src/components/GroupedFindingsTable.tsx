import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { Badge } from "./Badge";
import { DispositionSelect } from "./DispositionSelect";
import { DispositionHistory } from "./DispositionHistory";
import { FindingDetails } from "./FindingDetails";
import { BulkActionBar } from "./BulkActionBar";
import { timeAgo } from "../utils/timeAgo";
import type { Finding } from "../types";

interface TableGroup {
  schema: string;
  table: string;
  errors: number;
  warnings: number;
  findings: Finding[];
}

function groupFindings(findings: Finding[]): TableGroup[] {
  const map = new Map<string, TableGroup>();

  for (const f of findings) {
    const key = `${f.schema_name}.${f.table_name}`;
    let group = map.get(key);
    if (!group) {
      group = { schema: f.schema_name, table: f.table_name, errors: 0, warnings: 0, findings: [] };
      map.set(key, group);
    }
    if (f.severity === "error") group.errors++;
    else group.warnings++;
    group.findings.push(f);
  }

  const groups = Array.from(map.values());
  groups.sort((a, b) => {
    if (b.errors !== a.errors) return b.errors - a.errors;
    if (b.warnings !== a.warnings) return b.warnings - a.warnings;
    const nameA = `${a.schema}.${a.table}`;
    const nameB = `${b.schema}.${b.table}`;
    return nameA.localeCompare(nameB);
  });

  return groups;
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

interface GroupedFindingsTableProps {
  findings: Finding[];
}

export function GroupedFindingsTable({ findings }: GroupedFindingsTableProps) {
  const groups = groupFindings(findings);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [expandedFindingId, setExpandedFindingId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  if (groups.length === 0) {
    return <p className="text-center text-gray-400 py-8">No findings</p>;
  }

  const allKeys = groups.map((g) => `${g.schema}.${g.table}`);
  const allExpanded = allKeys.every((k) => expanded.has(k));

  const toggleAllGroups = () => {
    setExpanded(allExpanded ? new Set() : new Set(allKeys));
  };

  const toggle = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleGroupSelect = (group: TableGroup) => {
    const groupIds = group.findings.map((f) => f.id).filter((id): id is number => id !== null);
    const allGroupSelected = groupIds.every((id) => selectedIds.has(id));
    setSelectedIds((prev) => {
      const next = new Set(prev);
      for (const id of groupIds) {
        if (allGroupSelected) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  };

  return (
    <div className="mb-6">
      <BulkActionBar selectedIds={selectedIds} onClear={() => setSelectedIds(new Set())} />
      <div className="flex justify-end mb-2">
        <button
          onClick={toggleAllGroups}
          className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
        >
          {allExpanded ? "Collapse all" : "Expand all"}
        </button>
      </div>
      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
        {groups.map((group) => {
          const key = `${group.schema}.${group.table}`;
          const isOpen = expanded.has(key);
          const groupIds = group.findings.map((f) => f.id).filter((id): id is number => id !== null);
          const allGroupSelected = groupIds.length > 0 && groupIds.every((id) => selectedIds.has(id));

          return (
            <div key={key} className="border-b border-gray-100 dark:border-gray-800 last:border-b-0">
              <button
                onClick={() => toggle(key)}
                className={`w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left border-l-4 ${group.errors > 0 ? "border-l-red-500" : "border-l-amber-500"}`}
              >
                <span onClick={(e) => { e.stopPropagation(); toggleGroupSelect(group); }} className="flex-shrink-0">
                  <input
                    type="checkbox"
                    checked={allGroupSelected}
                    readOnly
                    className="rounded border-gray-300 dark:border-gray-600"
                  />
                </span>
                <span className="text-gray-400 text-xs w-4 flex-shrink-0">
                  {isOpen ? "\u25BC" : "\u25B6"}
                </span>
                <Link
                  to="/table/$schema/$table"
                  params={{ schema: group.schema, table: group.table }}
                  className="text-sm text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline font-medium"
                  onClick={(e) => e.stopPropagation()}
                >
                  {group.schema}.{group.table}
                </Link>
                <span className="flex-1" />
                {group.errors > 0 && (
                  <Badge type="error">
                    {group.errors} error{group.errors !== 1 ? "s" : ""}
                  </Badge>
                )}
                {group.warnings > 0 && (
                  <Badge type="warning">
                    {group.warnings} warning{group.warnings !== 1 ? "s" : ""}
                  </Badge>
                )}
              </button>

              {isOpen && (
                <div className="border-t border-gray-100 dark:border-gray-800">
                  {group.findings.map((f, i) => (
                    <div key={f.id ?? i}>
                      <div
                        className={`flex items-center gap-3 px-4 py-2.5 pl-11 text-sm hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors border-l-4 cursor-pointer ${getBorderClass(f)} ${getRowOpacity(f.disposition)}`}
                        onClick={() => setExpandedFindingId(expandedFindingId === f.id ? null : f.id)}
                      >
                        {f.id !== null && (
                          <span onClick={(e) => { e.stopPropagation(); toggleSelect(f.id!); }} className="flex-shrink-0">
                            <input
                              type="checkbox"
                              checked={selectedIds.has(f.id)}
                              readOnly
                              className="rounded border-gray-300 dark:border-gray-600"
                            />
                          </span>
                        )}
                        <span className="text-gray-500 dark:text-gray-400 w-20 flex-shrink-0">{f.check_type}</span>
                        <span className="w-20 flex-shrink-0">
                          <Badge type={f.severity}>{f.severity}</Badge>
                        </span>
                        <span className="text-gray-700 dark:text-gray-300 flex-1">{f.description}</span>
                        <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap flex-shrink-0">{timeAgo(f.created_at)}</span>
                        <DispositionSelect findingId={f.id} currentDisposition={f.disposition} />
                      </div>
                      {expandedFindingId === f.id && f.id !== null && (
                        <div className="pl-11 pr-4 py-2 bg-gray-50 dark:bg-gray-800/50 border-l-4 border-l-gray-200 dark:border-l-gray-700">
                          <FindingDetails finding={f} />
                          <DispositionHistory findingId={f.id} />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
