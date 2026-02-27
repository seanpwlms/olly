import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface VolumeTrendChartProps {
  data: { snapshot: string; row_count: number }[];
}

export function VolumeTrendChart({ data }: VolumeTrendChartProps) {
  if (data.length === 0) return null;
  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-5 mb-6">
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-4">
        Volume Trend
      </h2>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="snapshot"
            tickFormatter={(v: string) => v.slice(5, 10)}
          />
          <YAxis />
          <Tooltip
            labelFormatter={(v: string) => v.replace("T", " ").slice(0, 16)}
          />
          <Line
            type="monotone"
            dataKey="row_count"
            stroke="#3b82f6"
            dot={{ r: 3 }}
            name="Row Count"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
