import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { Badge } from "./Badge";
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

interface GroupedFindingsTableProps {
  findings: Finding[];
}

export function GroupedFindingsTable({ findings }: GroupedFindingsTableProps) {
  const groups = groupFindings(findings);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (groups.length === 0) {
    return <p className="text-center text-gray-400 py-8">No findings</p>;
  }

  const allKeys = groups.map((g) => `${g.schema}.${g.table}`);
  const allExpanded = allKeys.every((k) => expanded.has(k));

  const toggleAll = () => {
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

  return (
    <div className="mb-6">
      <div className="flex justify-end mb-2">
        <button
          onClick={toggleAll}
          className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
        >
          {allExpanded ? "Collapse all" : "Expand all"}
        </button>
      </div>
      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
        {groups.map((group) => {
          const key = `${group.schema}.${group.table}`;
          const isOpen = expanded.has(key);

          return (
            <div key={key} className="border-b border-gray-100 dark:border-gray-800 last:border-b-0">
              <button
                onClick={() => toggle(key)}
                className={`w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left border-l-4 ${group.errors > 0 ? "border-l-red-500" : "border-l-amber-500"}`}
              >
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
                    <div
                      key={i}
                      className={`flex items-center gap-3 px-4 py-2.5 pl-11 text-sm hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors border-l-4 ${f.severity === "error" ? "border-l-red-500" : f.severity === "warning" ? "border-l-amber-500" : "border-l-emerald-500"}`}
                    >
                      <span className="text-gray-500 dark:text-gray-400 w-20 flex-shrink-0">{f.check_type}</span>
                      <span className="w-20 flex-shrink-0">
                        <Badge type={f.severity}>{f.severity}</Badge>
                      </span>
                      <span className="text-gray-700 dark:text-gray-300">{f.description}</span>
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
