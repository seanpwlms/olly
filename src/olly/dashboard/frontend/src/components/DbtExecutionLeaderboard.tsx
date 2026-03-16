import { useState } from "react";
import { Badge } from "./Badge";
import { DataTable, type Column } from "./DataTable";
import { DbtNodeTimingChart } from "./DbtNodeTimingChart";
import type { DbtExecutionLeaderboardEntry } from "../types";

interface Props {
  entries: DbtExecutionLeaderboardEntry[];
}

function shortNodeId(uniqueId: string): string {
  const idx = uniqueId.indexOf(".");
  return idx >= 0 ? uniqueId.slice(idx + 1) : uniqueId;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s.toFixed(0)}s`;
}

function timeBarColor(seconds: number): string {
  if (seconds >= 300) return "bg-red-500";
  if (seconds >= 60) return "bg-amber-500";
  return "bg-blue-500";
}

export function DbtExecutionLeaderboard({ entries }: Props) {
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const maxTime = entries.length > 0 ? (entries[0]?.execution_time ?? 1) : 1;

  const rankMap = new Map(entries.map((e, i) => [e.unique_id, i + 1]));

  const columns: Column<DbtExecutionLeaderboardEntry>[] = [
    {
      key: "rank",
      header: "#",
      render: (e) => (
        <span className="text-gray-400 text-xs">{rankMap.get(e.unique_id)}</span>
      ),
    },
    {
      key: "unique_id",
      header: "Node",
      render: (e) => (
        <button
          className="text-blue-600 dark:text-blue-400 hover:underline text-left cursor-pointer"
          onClick={() =>
            setSelectedNode(selectedNode === e.unique_id ? null : e.unique_id)
          }
        >
          {shortNodeId(e.unique_id)}
        </button>
      ),
    },
    {
      key: "resource_type",
      header: "Type",
      render: (e) => (
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {e.resource_type}
        </span>
      ),
    },
    {
      key: "execution_time",
      header: "Time",
      render: (e) => (
        <div className="flex items-center gap-2 min-w-[140px]">
          <div className="flex-1 h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${timeBarColor(e.execution_time)}`}
              style={{
                width: `${Math.max(2, (e.execution_time / maxTime) * 100)}%`,
              }}
            />
          </div>
          <span className="text-xs font-mono whitespace-nowrap">
            {formatDuration(e.execution_time)}
          </span>
        </div>
      ),
    },
    {
      key: "severity",
      header: "Status",
      render: (e) => <Badge type={e.severity}>{e.status}</Badge>,
    },
  ];

  return (
    <section className="mb-6">
      <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">
        Slowest Nodes
      </h2>
      <DataTable
        data={entries}
        columns={columns}
        rowKey={(e) => e.unique_id}
        emptyMessage="No execution data"
      />
      {selectedNode && (
        <div className="mt-4">
          <DbtNodeTimingChart uniqueId={selectedNode} />
        </div>
      )}
    </section>
  );
}
