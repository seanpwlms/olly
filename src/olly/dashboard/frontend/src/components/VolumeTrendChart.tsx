import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { Finding } from "../types";

interface VolumeTrendChartProps {
  data: { snapshot: string; row_count: number }[];
  findings?: Finding[];
  schemaDiffTimestamp?: string | null;
}

function formatDateLabel(v: string): string {
  const d = new Date(v.length > 10 ? v : v + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function toTimestamp(v: string): number {
  return new Date(v.length > 10 ? v : v + "T00:00:00").getTime();
}

export function VolumeTrendChart({ data, findings, schemaDiffTimestamp }: VolumeTrendChartProps) {
  if (data.length === 0) return null;
  const grid = "var(--chart-grid)";
  const axis = "var(--chart-axis)";

  // Convert to numeric timestamps so the x-axis respects actual time distances
  const timeData = data.map((d) => ({ ...d, _ts: toTimestamp(d.snapshot) }));

  // Collect annotation timestamps from error-severity findings
  const annotationTimestamps = new Set<number>();
  if (findings) {
    for (const f of findings) {
      if (f.severity === "error") {
        const match = timeData.find((d) => d.snapshot.slice(0, 10) === (f.details.snapshot_time as string | undefined)?.slice(0, 10));
        if (match) annotationTimestamps.add(match._ts);
      }
    }
  }

  const schemaDiffTs = schemaDiffTimestamp
    ? timeData.find((d) => d.snapshot.slice(0, 10) === schemaDiffTimestamp.slice(0, 10))?._ts
    : undefined;

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-5 mb-6">
      <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
        Volume Trend
      </h2>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={timeData}>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} />
          <XAxis
            dataKey="_ts"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(v: number) => formatDateLabel(new Date(v).toISOString())}
            stroke={axis}
            tick={{ fontSize: 12 }}
          />
          <YAxis
            stroke={axis}
            tick={{ fontSize: 12 }}
            tickFormatter={(v: number) => v.toLocaleString()}
          />
          <Tooltip
            labelFormatter={(v: number) => formatDateLabel(new Date(v).toISOString())}
            formatter={(v: number) => [v.toLocaleString(), "Row count"]}
            contentStyle={{ backgroundColor: "var(--chart-bg)", border: "1px solid var(--chart-grid)" }}
          />
          {schemaDiffTs != null && (
            <ReferenceLine
              x={schemaDiffTs}
              stroke="var(--chart-axis)"
              strokeDasharray="4 4"
              label={{ value: "schema change", position: "top", fontSize: 12, fill: "var(--chart-axis)" }}
            />
          )}
          {Array.from(annotationTimestamps).map((ts) => (
            <ReferenceLine
              key={ts}
              x={ts}
              stroke="var(--color-red-500)"
              strokeDasharray="4 4"
              label={{ value: "error", position: "top", fontSize: 12, fill: "var(--color-red-500)" }}
            />
          ))}
          <Line
            type="monotone"
            dataKey="row_count"
            stroke="var(--color-accent-500)"
            dot={{ r: 3 }}
            name="Row count"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
