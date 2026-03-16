import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useDbtNodeTimings } from "../hooks/queries";
import { SkeletonTable } from "./Skeleton";

interface Props {
  uniqueId: string;
}

function formatDateLabel(v: string): string {
  const d = new Date(v.length > 10 ? v : v + "T00:00:00");
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s.toFixed(0)}s`;
}

function shortNodeId(uniqueId: string): string {
  const idx = uniqueId.indexOf(".");
  return idx >= 0 ? uniqueId.slice(idx + 1) : uniqueId;
}

export function DbtNodeTimingChart({ uniqueId }: Props) {
  const { data, isLoading } = useDbtNodeTimings(uniqueId);

  if (isLoading) return <SkeletonTable rows={3} cols={2} />;
  if (!data || data.timings.length < 2) {
    return (
      <div className="text-sm text-gray-500 dark:text-gray-400 py-2">
        Not enough historical data for {shortNodeId(uniqueId)}.
      </div>
    );
  }

  const grid = "var(--chart-grid)";
  const axis = "var(--chart-axis)";

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm p-4">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
        {shortNodeId(uniqueId)} — Execution Time History
      </h3>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data.timings}>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} />
          <XAxis
            dataKey="timestamp"
            tickFormatter={formatDateLabel}
            stroke={axis}
            tick={{ fontSize: 10 }}
          />
          <YAxis
            stroke={axis}
            tick={{ fontSize: 10 }}
            tickFormatter={formatDuration}
          />
          <Tooltip
            labelFormatter={formatDateLabel}
            formatter={(v: number) => [formatDuration(v), "Duration"]}
            contentStyle={{
              backgroundColor: "var(--chart-bg)",
              border: "1px solid var(--chart-grid)",
            }}
          />
          <Line
            type="monotone"
            dataKey="execution_time"
            stroke="#8b5cf6"
            dot={{ r: 2 }}
            name="Duration"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
