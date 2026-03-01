import { useNavigate } from "@tanstack/react-router";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Brush,
} from "recharts";
import type { FindingsTrendPoint } from "../types";

function formatDateLabel(v: string): string {
  const d = new Date(v + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Fill gaps so every calendar day gets a data point (carries forward last known values). */
function fillDayGaps(points: FindingsTrendPoint[]): (FindingsTrendPoint & { label: string })[] {
  if (points.length === 0) return [];
  const byDay = new Map<string, FindingsTrendPoint>();
  for (const p of points) {
    const day = p.timestamp.slice(0, 10);
    // keep the latest entry per day
    if (!byDay.has(day) || p.timestamp > byDay.get(day)!.timestamp) {
      byDay.set(day, p);
    }
  }
  const sortedDays = [...byDay.keys()].sort();
  const result: (FindingsTrendPoint & { label: string })[] = [];
  const start = new Date(sortedDays[0] + "T00:00:00");
  const end = new Date(sortedDays[sortedDays.length - 1] + "T00:00:00");
  let prev = byDay.get(sortedDays[0])!;
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const key = d.toISOString().slice(0, 10);
    const point = byDay.get(key) ?? { timestamp: key, errors: prev.errors, warnings: prev.warnings };
    result.push({ ...point, label: key });
    prev = point;
  }
  return result;
}

export function FindingsTrendChart({ data }: { data: FindingsTrendPoint[] }) {
  const navigate = useNavigate();

  const trendData = fillDayGaps(data);

  if (trendData.length <= 1) return null;

  const grid = "var(--chart-grid)";
  const axis = "var(--chart-axis)";

  return (
    <section className="mb-6">
      <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Findings Trend</h2>
      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm p-4">
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart
            data={trendData}
            onClick={(state) => {
              if (state?.activePayload?.[0]?.payload?.timestamp) {
                const ts = state.activePayload[0].payload.timestamp as string;
                void navigate({ to: "/findings", search: { q: ts.slice(0, 10) } });
              }
            }}
            style={{ cursor: "pointer" }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke={grid} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke={axis} tickFormatter={formatDateLabel} />
            <YAxis allowDecimals={false} tick={{ fontSize: 11 }} stroke={axis} />
            <Tooltip
              labelFormatter={(v: string) => formatDateLabel(v)}
              formatter={(v: number, name: string) => [v.toLocaleString(), name]}
              contentStyle={{ backgroundColor: "var(--chart-bg)", border: "1px solid var(--chart-grid)" }}
            />
            <Legend />
            <Area type="monotone" dataKey="errors" name="Errors" stroke="#ef4444" fill="#fee2e2" strokeWidth={2} />
            <Area type="monotone" dataKey="warnings" name="Warnings" stroke="#f59e0b" fill="#fef3c7" strokeWidth={2} />
            {trendData.length > 5 && (
              <Brush dataKey="label" height={24} stroke="var(--chart-axis)" fill="var(--chart-bg)" tickFormatter={formatDateLabel} />
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
