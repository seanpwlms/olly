import { Badge } from "./Badge";
import { DataTable, type Column } from "./DataTable";
import { DispositionSelect } from "./DispositionSelect";
import { DispositionHistory } from "./DispositionHistory";
import { FindingDetails } from "./FindingDetails";
import { TableRef } from "./TableRef";
import { RelativeTime } from "./RelativeTime";
import type { Finding } from "../types";

interface FindingsTableProps {
  findings: Finding[];
  showLink?: boolean;
  /** Selection is owned by the page so it survives switching views. */
  selected: Set<number>;
  onSelectionChange: (next: Set<number>) => void;
}

/** Handled findings stay visible but recede. Severity is shown once, by the badge. */
function rowOpacity(f: Finding): string {
  if (f.disposition === "completed") return "opacity-50";
  if (f.disposition === "no_action") return "opacity-60";
  return "";
}

/**
 * Columns shared by the flat and grouped findings views. Fixed widths let the
 * grouped view's per-table tables line up with each other.
 */
export function findingColumns({ table, showLink = true }: { table: boolean; showLink?: boolean }): Column<Finding>[] {
  const columns: Column<Finding>[] = [
    { key: "check_type", header: "Check", className: "w-28", render: (f) => f.check_type },
    {
      key: "severity",
      header: "Severity",
      className: "w-24",
      render: (f) => <Badge type={f.severity}>{f.severity}</Badge>,
    },
  ];
  if (table) {
    columns.push({
      key: "table",
      header: "Table",
      render: (f) => <TableRef schema={f.schema_name} table={f.table_name} plain={!showLink} />,
    });
  }
  columns.push(
    { key: "description", header: "Description", render: (f) => f.description },
    {
      key: "when",
      header: "When",
      className: "w-24 whitespace-nowrap",
      render: (f) => <RelativeTime value={f.created_at} className="text-xs text-gray-500 dark:text-gray-400" />,
    },
    {
      key: "status",
      header: "Status",
      className: "w-36",
      render: (f) => (
        <span onClick={(e) => e.stopPropagation()}>
          <DispositionSelect findingId={f.id} currentDisposition={f.disposition} />
        </span>
      ),
    },
  );
  return columns;
}

/** Selection adapter: the page tracks numeric ids, DataTable tracks string keys. */
export function findingSelection(selected: Set<number>, onChange: (next: Set<number>) => void) {
  return {
    keyFor: (f: Finding) => (f.id !== null ? String(f.id) : null),
    selected: new Set([...selected].map(String)),
    onChange: (next: Set<string>) => onChange(new Set([...next].map(Number))),
    headerToggle: false,
  };
}

export function findingRowKey(f: Finding) {
  return String(f.id ?? `${f.check_type}:${f.schema_name}.${f.table_name}:${f.description}`);
}

export function findingExpanded(f: Finding) {
  return (
    <>
      <FindingDetails finding={f} />
      {f.id !== null && <DispositionHistory findingId={f.id} />}
    </>
  );
}

export { rowOpacity as findingRowClass };

export function FindingsTable({
  findings,
  showLink = true,
  selected,
  onSelectionChange,
}: FindingsTableProps) {
  return (
    <DataTable
      data={findings}
      columns={findingColumns({ table: true, showLink })}
      rowKey={findingRowKey}
      rowClassName={rowOpacity}
      emptyMessage="No findings"
      selection={findingSelection(selected, onSelectionChange)}
      expandedContent={findingExpanded}
    />
  );
}
