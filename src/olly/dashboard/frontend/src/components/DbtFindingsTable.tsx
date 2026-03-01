import { Badge } from "./Badge";
import { DataTable, type Column } from "./DataTable";
import type { DbtFinding } from "../types";

interface DbtFindingsTableProps {
  findings: DbtFinding[];
  onShowSql?: (sql: string, nodeId: string) => void;
}

function shortNodeId(uniqueId: string): string {
  const idx = uniqueId.indexOf(".");
  return idx >= 0 ? uniqueId.slice(idx + 1) : uniqueId;
}

export function DbtFindingsTable({ findings, onShowSql }: DbtFindingsTableProps) {
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
      render: (f) => shortNodeId(f.unique_id),
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
                onShowSql(f.details.compiled_code as string, f.unique_id)
              }
            >
              View SQL
            </button>
          )}
        </>
      ),
    },
  ];

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
