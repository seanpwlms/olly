import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface CostDailyChartProps {
  data: { day: string; cost: number }[];
}

export function CostDailyChart({ data }: CostDailyChartProps) {
  if (data.length === 0) return null;
  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-5 mb-6">
      <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-4">
        Cost by Day (Last 30 Days)
      </h3>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="day" tickFormatter={(v: string) => v.slice(5, 10)} />
          <YAxis tickFormatter={(v: number) => `$${v.toFixed(2)}`} />
          <Tooltip
            formatter={(v: number) => [`$${v.toFixed(2)}`, "Cost (USD)"]}
          />
          <Line
            type="monotone"
            dataKey="cost"
            stroke="#3b82f6"
            dot={{ r: 3 }}
            name="Cost"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
