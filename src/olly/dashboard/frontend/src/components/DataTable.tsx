import { Fragment, useState, type ReactNode } from "react";
import { Chevron } from "./Chevron";

export interface Column<T> {
  key: string;
  header: string | ReactNode;
  render: (row: T) => ReactNode;
  sortable?: boolean;
  align?: "left" | "right";
  /** Extra classes for this column's header and cells, e.g. a fixed width. */
  className?: string;
}

/** Row selection via a checkbox column. */
export interface DataTableSelection<T> {
  /** Selection key for a row, or null when the row cannot be selected. */
  keyFor: (row: T) => string | null;
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  /** Set false when a surrounding toolbar already offers select-all. */
  headerToggle?: boolean;
}

interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  /** Extra classes for a row, e.g. dimming rows that are already handled. */
  rowClassName?: (row: T) => string;
  sort?: { column: string; order: "asc" | "desc" };
  onSort?: (column: string) => void;
  emptyMessage?: string;
  /** When given, rows expand to show this content in a full-width row. */
  expandedContent?: (row: T) => ReactNode;
  selection?: DataTableSelection<T>;
  /** Omit the header row, e.g. when the table sits under a group heading. */
  hideHeader?: boolean;
  /** Fixed layout, so several stacked tables line up column-for-column. */
  fixed?: boolean;
  className?: string;
}

const headerCell = "px-3 py-2.5 text-xs font-medium text-gray-500 dark:text-gray-400";

function SortIndicator({ column, sort }: { column: string; sort?: { column: string; order: "asc" | "desc" } }) {
  if (!sort || column !== sort.column) return null;
  return <span aria-hidden="true">{sort.order === "asc" ? " ↑" : " ↓"}</span>;
}

export function DataTable<T>({
  data,
  columns,
  rowKey,
  onRowClick,
  rowClassName,
  sort,
  onSort,
  emptyMessage = "No data",
  expandedContent,
  selection,
  hideHeader = false,
  fixed = false,
  className = "mb-6",
}: DataTableProps<T>) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  if (data.length === 0) {
    return <p className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">{emptyMessage}</p>;
  }

  const selectableKeys = selection
    ? data.map(selection.keyFor).filter((k): k is string => k !== null)
    : [];
  const allSelected =
    selectableKeys.length > 0 && selectableKeys.every((k) => selection!.selected.has(k));

  const toggleAll = () => {
    if (!selection) return;
    const next = new Set(selection.selected);
    for (const k of selectableKeys) {
      if (allSelected) next.delete(k);
      else next.add(k);
    }
    selection.onChange(next);
  };

  const toggleOne = (key: string) => {
    if (!selection) return;
    const next = new Set(selection.selected);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    selection.onChange(next);
  };

  const colSpan = columns.length + (selection ? 1 : 0) + (expandedContent ? 1 : 0);
  const isRowInteractive = !!onRowClick || !!expandedContent;

  return (
    // Wide tables scroll inside this wrapper instead of making the page scroll sideways.
    <div className={`overflow-x-auto ${className}`}>
      <table className={`w-full ${fixed ? "table-fixed min-w-[40rem]" : ""}`}>
        {!hideHeader && (
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-800">
              {selection && (
                <th className="w-9 px-3 py-2.5">
                  {selection.headerToggle !== false && (
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleAll}
                      aria-label="Select all rows"
                      className="rounded border-gray-300 dark:border-gray-600"
                    />
                  )}
                </th>
              )}
              {expandedContent && <th className="w-8 py-2.5" />}
              {columns.map((col) => {
                const isSortable = col.sortable && onSort;
                const align = col.align === "right" ? "text-right" : "text-left";
                return (
                  <th
                    key={col.key}
                    className={`${headerCell} ${align} ${col.className ?? ""}`}
                    aria-sort={
                      sort?.column === col.key ? (sort.order === "asc" ? "ascending" : "descending") : undefined
                    }
                  >
                    {isSortable ? (
                      <button
                        type="button"
                        onClick={() => onSort(col.key)}
                        className="cursor-pointer font-medium hover:text-gray-900 dark:hover:text-gray-100"
                      >
                        {col.header}
                        <SortIndicator column={col.key} sort={sort} />
                      </button>
                    ) : (
                      col.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
        )}
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800/70">
          {data.map((row) => {
            const key = rowKey(row);
            const selectionKey = selection?.keyFor(row) ?? null;
            const expanded = !!expandedContent && expandedKey === key;
            const toggleExpanded = () => setExpandedKey(expanded ? null : key);
            return (
              <Fragment key={key}>
                <tr
                  className={`hover:bg-gray-100/60 dark:hover:bg-gray-800/40 transition-colors ${rowClassName?.(row) ?? ""}${isRowInteractive ? " cursor-pointer" : ""}`}
                  onClick={
                    isRowInteractive
                      ? () => {
                          onRowClick?.(row);
                          if (expandedContent) toggleExpanded();
                        }
                      : undefined
                  }
                >
                  {selection && (
                    <td className="w-9 px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                      {selectionKey !== null && (
                        <input
                          type="checkbox"
                          checked={selection.selected.has(selectionKey)}
                          onChange={() => toggleOne(selectionKey)}
                          aria-label="Select row"
                          className="rounded border-gray-300 dark:border-gray-600"
                        />
                      )}
                    </td>
                  )}
                  {expandedContent && (
                    <td className="w-8 py-2.5">
                      {/* The row is clickable for mouse users; this button is the keyboard path. */}
                      <button
                        type="button"
                        aria-expanded={expanded}
                        aria-label={expanded ? "Hide details" : "Show details"}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleExpanded();
                        }}
                        className="flex cursor-pointer items-center rounded p-0.5 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                      >
                        <Chevron open={expanded} />
                      </button>
                    </td>
                  )}
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={`px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 ${col.align === "right" ? "text-right" : ""} ${col.className ?? ""}`}
                    >
                      {col.render(row)}
                    </td>
                  ))}
                </tr>
                {expanded && (
                  <tr>
                    <td colSpan={colSpan} className="bg-gray-100/60 px-8 py-3 dark:bg-gray-900">
                      {expandedContent(row)}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
