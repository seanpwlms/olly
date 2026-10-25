import { useState } from "react";
import { Chevron } from "./Chevron";
import { DataTable } from "./DataTable";
import { TableRef } from "./TableRef";
import {
  findingColumns,
  findingExpanded,
  findingRowClass,
  findingRowKey,
  findingSelection,
} from "./FindingsTable";
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

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

interface GroupedFindingsTableProps {
  findings: Finding[];
  /** Selection is owned by the page so it survives switching views. */
  selected: Set<number>;
  onSelectionChange: (next: Set<number>) => void;
}

export function GroupedFindingsTable({
  findings,
  selected: selectedIds,
  onSelectionChange,
}: GroupedFindingsTableProps) {
  const groups = groupFindings(findings);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (groups.length === 0) {
    return <p className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">No findings</p>;
  }

  const allKeys = groups.map((g) => `${g.schema}.${g.table}`);
  const allExpanded = allKeys.every((k) => expanded.has(k));
  const columns = findingColumns({ table: false });
  const selection = findingSelection(selectedIds, onSelectionChange);

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

  const toggleGroupSelect = (group: TableGroup) => {
    const groupIds = group.findings.map((f) => f.id).filter((id): id is number => id !== null);
    const allGroupSelected = groupIds.every((id) => selectedIds.has(id));
    const next = new Set(selectedIds);
    for (const id of groupIds) {
      if (allGroupSelected) next.delete(id);
      else next.add(id);
    }
    onSelectionChange(next);
  };

  return (
    <div className="mb-6">
      <div className="flex justify-end mb-2">
        <button
          type="button"
          onClick={toggleAllGroups}
          className="cursor-pointer text-sm text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
        >
          {allExpanded ? "Collapse all" : "Expand all"}
        </button>
      </div>
      <div className="border-t border-gray-200 dark:border-gray-800">
        {groups.map((group) => {
          const key = `${group.schema}.${group.table}`;
          const isOpen = expanded.has(key);
          const panelId = `group-${key}`;
          const groupIds = group.findings.map((f) => f.id).filter((id): id is number => id !== null);
          const allGroupSelected = groupIds.length > 0 && groupIds.every((id) => selectedIds.has(id));

          return (
            <section key={key} className="border-b border-gray-200 dark:border-gray-800">
              {/* Row click toggles for mouse users; the chevron button is the accessible control. */}
              <div
                className="flex cursor-pointer items-center gap-3 px-3 py-2.5 hover:bg-gray-100/60 dark:hover:bg-gray-800/40 transition-colors"
                onClick={() => toggle(key)}
              >
                <input
                  type="checkbox"
                  checked={allGroupSelected}
                  onChange={() => toggleGroupSelect(group)}
                  onClick={(e) => e.stopPropagation()}
                  disabled={groupIds.length === 0}
                  aria-label={`Select all findings for ${key}`}
                  className="rounded border-gray-300 dark:border-gray-600"
                />
                <button
                  type="button"
                  aria-expanded={isOpen}
                  aria-controls={panelId}
                  aria-label={`${isOpen ? "Collapse" : "Expand"} ${key}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggle(key);
                  }}
                  className="flex cursor-pointer items-center rounded p-0.5 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                >
                  <Chevron open={isOpen} />
                </button>
                <TableRef schema={group.schema} table={group.table} className="text-sm font-medium" />
                <span className="ml-auto flex items-center gap-3 text-sm">
                  {group.errors > 0 && (
                    <span className="font-medium text-red-600 dark:text-red-400">{plural(group.errors, "error")}</span>
                  )}
                  {group.warnings > 0 && (
                    <span className="font-medium text-amber-700 dark:text-amber-400">{plural(group.warnings, "warning")}</span>
                  )}
                </span>
              </div>

              {isOpen && (
                <div id={panelId} className="pl-9">
                  <DataTable
                    data={group.findings}
                    columns={columns}
                    rowKey={findingRowKey}
                    rowClassName={findingRowClass}
                    selection={selection}
                    expandedContent={findingExpanded}
                    hideHeader
                    fixed
                    className="mb-2 border-t border-gray-100 dark:border-gray-800/70"
                  />
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
