import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Brush,
} from "recharts";

interface CostDailyChartProps {
  data: { day: string; cost: number }[];
}

function formatDateLabel(v: string): string {
  const d = new Date(v + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function CostDailyChart({ data }: CostDailyChartProps) {
  if (data.length === 0) return null;
  const grid = "var(--chart-grid)";
  const axis = "var(--chart-axis)";
  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm p-5 mb-6">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-4">
        Cost by Day (Last 30 Days)
      </h3>
      <ResponsiveContainer width="100%" height={data.length > 5 ? 290 : 250}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} />
          <XAxis dataKey="day" tickFormatter={formatDateLabel} stroke={axis} tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v: number) => `$${v.toFixed(2)}`} stroke={axis} tick={{ fontSize: 11 }} />
          <Tooltip
            labelFormatter={(v: string) => formatDateLabel(v)}
            formatter={(v: number) => [`$${v.toFixed(2)}`, "Cost (USD)"]}
            contentStyle={{ backgroundColor: "var(--chart-bg)", border: "1px solid var(--chart-grid)" }}
          />
          <Line
            type="monotone"
            dataKey="cost"
            stroke="#3b82f6"
            dot={{ r: 3 }}
            name="Cost"
          />
          {data.length > 5 && (
            <Brush dataKey="day" height={24} stroke={axis} fill="var(--chart-bg)" tickFormatter={formatDateLabel} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
