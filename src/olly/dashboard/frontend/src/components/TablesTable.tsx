import { Link } from "@tanstack/react-router";
import type { TableRow } from "../types";

interface TablesTableProps {
  tables: TableRow[];
  sort: string;
  order: string;
  onSort: (column: string) => void;
}

function SortIndicator({ column, sort, order }: { column: string; sort: string; order: string }) {
  if (column !== sort) return null;
  return <span>{order === "asc" ? " \u25B2" : " \u25BC"}</span>;
}

export function TablesTable({ tables, sort, order, onSort }: TablesTableProps) {
  if (tables.length === 0) {
    return <p className="text-center text-gray-400 py-8">No tables found</p>;
  }
  return (
    <table className="w-full bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden mb-6">
      <thead>
        <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide cursor-pointer select-none hover:text-gray-800 dark:hover:text-gray-200" onClick={() => onSort("schema")}>
            Schema
            <SortIndicator column="schema" sort={sort} order={order} />
          </th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide cursor-pointer select-none hover:text-gray-800 dark:hover:text-gray-200" onClick={() => onSort("table")}>
            Table
            <SortIndicator column="table" sort={sort} order={order} />
          </th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide cursor-pointer select-none hover:text-gray-800 dark:hover:text-gray-200" onClick={() => onSort("type")}>
            Type
            <SortIndicator column="type" sort={sort} order={order} />
          </th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide cursor-pointer select-none hover:text-gray-800 dark:hover:text-gray-200" onClick={() => onSort("columns")}>
            Columns
            <SortIndicator column="columns" sort={sort} order={order} />
          </th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide cursor-pointer select-none hover:text-gray-800 dark:hover:text-gray-200" onClick={() => onSort("row_count")}>
            Rows
            <SortIndicator column="row_count" sort={sort} order={order} />
          </th>
          <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Status</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
        {tables.map((t) => (
          <tr key={`${t.schema}.${t.table}`} className="hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{t.schema}</td>
            <td className="px-4 py-3 text-sm">
              <Link
                to="/table/$schema/$table"
                params={{ schema: t.schema, table: t.table }}
                className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
              >
                {t.table}
              </Link>
            </td>
            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{t.type}</td>
            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{t.columns}</td>
            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{t.row_count != null ? t.row_count.toLocaleString() : "\u2014"}</td>
            <td className="px-4 py-3 text-sm">
              {t.error_count > 0 && (
                <span className="text-sm font-semibold text-red-600 dark:text-red-400">
                  {t.error_count} error{t.error_count !== 1 ? "s" : ""}
                </span>
              )}{" "}
              {t.warning_count > 0 && (
                <span className="text-sm font-semibold text-amber-600 dark:text-amber-400">
                  {t.warning_count} warning{t.warning_count !== 1 ? "s" : ""}
                </span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
