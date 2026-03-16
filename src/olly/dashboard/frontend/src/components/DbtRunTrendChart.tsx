import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Bar,
  ComposedChart,
} from "recharts";
import type { DbtRunHistoryPoint } from "../types";

interface Props {
  data: DbtRunHistoryPoint[];
}

function formatDateLabel(v: string): string {
  const d = new Date(v.length > 10 ? v : v + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s.toFixed(0)}s`;
}

export function DbtRunTrendChart({ data }: Props) {
  if (data.length < 2) return null;

  const grid = "var(--chart-grid)";
  const axis = "var(--chart-axis)";

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm p-5 mb-6">
      <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-4">
        Run Duration Trend
      </h2>
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} />
          <XAxis
            dataKey="created_at"
            tickFormatter={formatDateLabel}
            stroke={axis}
            tick={{ fontSize: 11 }}
          />
          <YAxis
            yAxisId="time"
            stroke={axis}
            tick={{ fontSize: 11 }}
            tickFormatter={formatDuration}
          />
          <YAxis
            yAxisId="count"
            orientation="right"
            stroke={axis}
            tick={{ fontSize: 11 }}
            hide
          />
          <Tooltip
            labelFormatter={formatDateLabel}
            formatter={(value: number, name: string) => {
              if (name === "elapsed_time") return [formatDuration(value), "Duration"];
              if (name === "error_count") return [value, "Errors"];
              return [value, name];
            }}
            contentStyle={{
              backgroundColor: "var(--chart-bg)",
              border: "1px solid var(--chart-grid)",
            }}
          />
          <Bar
            yAxisId="count"
            dataKey="error_count"
            fill="#ef444440"
            name="error_count"
          />
          <Line
            yAxisId="time"
            type="monotone"
            dataKey="elapsed_time"
            stroke="#3b82f6"
            dot={{ r: 3 }}
            name="elapsed_time"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
