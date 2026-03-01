import { Link } from "@tanstack/react-router";
import { DataTable, type Column } from "./DataTable";
import type { TableRow } from "../types";

interface TablesTableProps {
  tables: TableRow[];
  sort: string;
  order: string;
  onSort: (column: string) => void;
}

export function TablesTable({ tables, sort, order, onSort }: TablesTableProps) {
  const columns: Column<TableRow>[] = [
    {
      key: "schema",
      header: "Schema",
      sortable: true,
      render: (t) => t.schema,
    },
    {
      key: "table",
      header: "Table",
      sortable: true,
      render: (t) => (
        <Link
          to="/table/$schema/$table"
          params={{ schema: t.schema, table: t.table }}
          className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
        >
          {t.table}
        </Link>
      ),
    },
    {
      key: "type",
      header: "Type",
      sortable: true,
      render: (t) => t.type,
    },
    {
      key: "columns",
      header: "Columns",
      sortable: true,
      render: (t) => t.columns,
    },
    {
      key: "row_count",
      header: "Rows",
      sortable: true,
      render: (t) => (t.row_count != null ? t.row_count.toLocaleString() : "\u2014"),
    },
    {
      key: "status",
      header: "Status",
      render: (t) => (
        <>
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
        </>
      ),
    },
  ];

  return (
    <DataTable
      data={tables}
      columns={columns}
      rowKey={(t) => `${t.schema}.${t.table}`}
      sort={{ column: sort, order: order as "asc" | "desc" }}
      onSort={onSort}
      emptyMessage="No tables found"
    />
  );
}
