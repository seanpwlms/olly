import { Badge } from "./Badge";
import { DataTable, type Column } from "./DataTable";
import type { DbtFinding } from "../types";

interface DbtFindingsTableProps {
  findings: DbtFinding[];
  onShowSql?: (sql: string, nodeId: string, dbtRunId: number | null) => void;
  compact?: boolean;
}

function shortNodeId(uniqueId: string): string {
  const idx = uniqueId.indexOf(".");
  return idx >= 0 ? uniqueId.slice(idx + 1) : uniqueId;
}

export function DbtFindingsTable({ findings, onShowSql, compact }: DbtFindingsTableProps) {
  const columns: Column<DbtFinding>[] = [
    {
      key: "severity",
      header: "Severity",
      render: (f) => <Badge type={f.severity}>{f.severity}</Badge>,
    },
    {
      key: "resource_type",
      header: "Type",
      render: (f) => f.resource_type,
    },
    {
      key: "unique_id",
      header: "Node",
      render: (f) => (
        <span className="break-all">
          {shortNodeId(f.unique_id)}
          {typeof f.details.cascade_root === "string" && (
            <span className="ml-1.5 px-1.5 py-0.5 text-[10px] bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 rounded">
              cascade
            </span>
          )}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (f) => f.status,
    },
    {
      key: "execution_time",
      header: "Time",
      render: (f) => `${f.execution_time.toFixed(1)}s`,
    },
  ];

  if (!compact) {
    columns.push(
      {
        key: "failures",
        header: "Failures",
        render: (f) => {
          const failures = f.details.failures;
          if (typeof failures === "number" && failures > 0) {
            return (
              <span className="text-red-600 dark:text-red-400 font-medium">
                {failures}
              </span>
            );
          }
          return <span className="text-gray-400">&mdash;</span>;
        },
      },
      {
        key: "description",
        header: "Description",
        render: (f) => (
          <>
            {f.description}
            {typeof f.details.compiled_code === "string" && onShowSql && (
              <button
                className="ml-2 px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded text-blue-600 dark:text-blue-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors cursor-pointer"
                onClick={() =>
                  onShowSql(f.details.compiled_code as string, f.unique_id, f.dbt_run_id ?? null)
                }
              >
                View SQL
              </button>
            )}
          </>
        ),
      },
    );
  } else {
    // Compact mode: just a SQL column
    columns.push({
      key: "sql",
      header: "SQL",
      render: (f) =>
        typeof f.details.compiled_code === "string" && onShowSql ? (
          <button
            className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded text-blue-600 dark:text-blue-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors cursor-pointer"
            onClick={() =>
              onShowSql(f.details.compiled_code as string, f.unique_id, f.dbt_run_id ?? null)
            }
          >
            View
          </button>
        ) : (
          <span className="text-gray-400">&mdash;</span>
        ),
    });
  }

  return (
    <DataTable
      data={findings}
      columns={columns}
      rowKey={(f) => f.unique_id}
      rowBorderColor={(f) =>
        f.severity === "error" ? "error" : f.severity === "warning" ? "warning" : "success"
      }
      emptyMessage="No dbt findings"
    />
  );
}
