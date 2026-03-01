import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string | ReactNode;
  render: (row: T) => ReactNode;
  sortable?: boolean;
}

interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  rowBorderColor?: (row: T) => "error" | "warning" | "success" | undefined;
  sort?: { column: string; order: "asc" | "desc" };
  onSort?: (column: string) => void;
  emptyMessage?: string;
}

const borderColorMap = {
  error: "border-l-red-500",
  warning: "border-l-amber-500",
  success: "border-l-emerald-500",
};

function SortIndicator({ column, sort }: { column: string; sort?: { column: string; order: "asc" | "desc" } }) {
  if (!sort || column !== sort.column) return null;
  return <span>{sort.order === "asc" ? " \u25B2" : " \u25BC"}</span>;
}

export function DataTable<T>({
  data,
  columns,
  rowKey,
  onRowClick,
  rowBorderColor,
  sort,
  onSort,
  emptyMessage = "No data",
}: DataTableProps<T>) {
  if (data.length === 0) {
    return <p className="text-center text-gray-400 py-8">{emptyMessage}</p>;
  }

  return (
    <table className="w-full bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden mb-6">
      <thead>
        <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
          {columns.map((col) => {
            const isSortable = col.sortable && onSort;
            return (
              <th
                key={col.key}
                className={`px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide${isSortable ? " cursor-pointer select-none hover:text-gray-800 dark:hover:text-gray-200" : ""}`}
                onClick={isSortable ? () => onSort(col.key) : undefined}
              >
                {col.header}
                {isSortable && <SortIndicator column={col.key} sort={sort} />}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
        {data.map((row) => {
          const border = rowBorderColor?.(row);
          const borderClass = border ? `border-l-4 ${borderColorMap[border]}` : "";
          return (
            <tr
              key={rowKey(row)}
              className={`hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors ${borderClass}${onRowClick ? " cursor-pointer" : ""}`}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((col) => (
                <td key={col.key} className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                  {col.render(row)}
                </td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
