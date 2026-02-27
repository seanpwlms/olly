import { useState } from "react";
import { useConnection } from "../hooks/useConnection";
import { useHistory } from "../hooks/queries";
import { StatCard } from "../components/StatCard";
import { StatsRow } from "../components/StatsRow";
import { EmptyState } from "../components/EmptyState";

export function HistoryPage() {
  const { connection } = useConnection();
  const [days, setDays] = useState(30);
  const { data, isLoading } = useHistory(connection, days);

  if (isLoading || !data) return <div className="text-center text-gray-500 py-8">Loading...</div>;

  const { snapshots } = data;

  return (
    <>
      <h1 className="text-2xl font-bold text-gray-900 mb-4">History</h1>

      <StatsRow>
        <StatCard
          value={snapshots.length}
          label={`Snapshots (${days} days)`}
        />
      </StatsRow>

      <section className="mb-6">
        <div className="flex justify-between items-center flex-wrap gap-2 mb-3">
          <h2 className="text-lg font-semibold text-gray-800">Date Range</h2>
          <div className="flex flex-wrap gap-2">
            <select
              className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
          </div>
        </div>
      </section>

      {snapshots.length > 0 ? (
        <section className="mb-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Recent Snapshots</h2>
          <table className="w-full bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden mb-6">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Snapshot ID</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Created At</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Tables Captured</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {snapshots.map((s) => (
                <tr key={s.snapshot_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-sm text-gray-700">{s.snapshot_id}</td>
                  <td className="px-4 py-3 text-sm text-gray-700">{s.created_at.slice(0, 16).replace("T", " ")}</td>
                  <td className="px-4 py-3 text-sm text-gray-700">{s.table_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : (
        <EmptyState message="No snapshots found for the selected date range." />
      )}
    </>
  );
}
