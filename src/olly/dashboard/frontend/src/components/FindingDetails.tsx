import type { Finding } from "../types";

function DetailGrid({ items }: { items: [string, string][] }) {
  if (items.length === 0) return null;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
      {items.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="font-medium text-gray-500 dark:text-gray-400">{label}</dt>
          <dd className="text-gray-700 dark:text-gray-300">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "\u2014";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2);
  return String(v);
}

function SchemaDetails({ d }: { d: Record<string, unknown> }) {
  const items: [string, string][] = [];
  if (d.change) items.push(["Change", fmt(d.change)]);
  if (d.column) items.push(["Column", fmt(d.column)]);
  if (d.old_type) items.push(["Old type", fmt(d.old_type)]);
  if (d.new_type) items.push(["New type", fmt(d.new_type)]);
  if (d.data_type) items.push(["Data type", fmt(d.data_type)]);
  if (d.old_nullable !== undefined) items.push(["Old nullable", d.old_nullable ? "yes" : "no"]);
  if (d.new_nullable !== undefined) items.push(["New nullable", d.new_nullable ? "yes" : "no"]);
  if (d.table_type) items.push(["Table type", fmt(d.table_type)]);
  return <DetailGrid items={items} />;
}

function VolumeDetails({ d }: { d: Record<string, unknown> }) {
  const items: [string, string][] = [];
  if (d.current_count !== undefined) items.push(["Row count", fmt(d.current_count)]);
  if (d.z_score !== undefined) items.push(["Z-score", fmt(d.z_score)]);
  if (d.threshold !== undefined) items.push(["Threshold", fmt(d.threshold)]);
  if (d.history_mean !== undefined) items.push(["History mean", fmt(d.history_mean)]);
  if (d.history_stdev !== undefined) items.push(["History stdev", fmt(d.history_stdev)]);
  if (d.history_depth !== undefined) items.push(["History depth", fmt(d.history_depth)]);
  return <DetailGrid items={items} />;
}

function FreshnessDetails({ d }: { d: Record<string, unknown> }) {
  const items: [string, string][] = [];
  if (d.column) items.push(["Column", fmt(d.column)]);
  if (d.max_timestamp) items.push(["Last update", fmt(d.max_timestamp)]);
  if (d.age_hours !== undefined) items.push(["Age", `${fmt(d.age_hours)}h`]);
  if (d.threshold_hours !== undefined) items.push(["Threshold", `${fmt(d.threshold_hours)}h`]);
  if (d.unchanged_snapshots !== undefined) items.push(["Unchanged snapshots", fmt(d.unchanged_snapshots)]);
  if (d.reason) items.push(["Reason", fmt(d.reason)]);
  return <DetailGrid items={items} />;
}

function IntegrityDetails({ d }: { d: Record<string, unknown> }) {
  const items: [string, string][] = [];
  if (d.pipeline) items.push(["Pipeline", fmt(d.pipeline)]);
  if (d.method) items.push(["Method", fmt(d.method)]);
  if (d.source_value !== undefined) items.push(["Source value", fmt(d.source_value)]);
  if (d.target_value !== undefined) items.push(["Target value", fmt(d.target_value)]);
  if (d.diff !== undefined) items.push(["Diff", fmt(d.diff)]);
  if (d.ratio !== undefined) items.push(["Ratio", fmt(d.ratio)]);
  if (d.source_hash) items.push(["Source hash", fmt(d.source_hash)]);
  if (d.target_hash) items.push(["Target hash", fmt(d.target_hash)]);
  if (d.tolerance_delta !== undefined && d.tolerance_delta !== null) items.push(["Tolerance delta", fmt(d.tolerance_delta)]);
  if (d.tolerance_ratio !== undefined && d.tolerance_ratio !== null) items.push(["Tolerance ratio", fmt(d.tolerance_ratio)]);
  return <DetailGrid items={items} />;
}

function ContractsDetails({ d }: { d: Record<string, unknown> }) {
  const items: [string, string][] = [];
  if (d.issue) items.push(["Issue", fmt(d.issue)]);
  if (d.column) items.push(["Column", fmt(d.column)]);
  if (d.expected) items.push(["Expected", fmt(d.expected)]);
  if (d.actual) items.push(["Actual", fmt(d.actual)]);
  return <DetailGrid items={items} />;
}

function CostDetails({ d }: { d: Record<string, unknown> }) {
  const items: [string, string][] = [];
  if (d.current_cost_usd !== undefined) items.push(["Current cost", `$${fmt(d.current_cost_usd)}`]);
  if (d.mean_cost_usd !== undefined) items.push(["Mean cost", `$${fmt(d.mean_cost_usd)}`]);
  if (d.z_score !== undefined) items.push(["Z-score", fmt(d.z_score)]);
  if (d.threshold !== undefined) items.push(["Threshold", fmt(d.threshold)]);
  return <DetailGrid items={items} />;
}

function FallbackDetails({ d }: { d: Record<string, unknown> }) {
  const items: [string, string][] = Object.entries(d).map(([k, v]) => [k, fmt(v)]);
  return <DetailGrid items={items} />;
}

interface FindingDetailsProps {
  finding: Finding;
}

export function FindingDetails({ finding }: FindingDetailsProps) {
  const d = finding.details;
  if (!d || Object.keys(d).length === 0) return null;

  const renderers: Record<string, ({ d }: { d: Record<string, unknown> }) => React.JSX.Element | null> = {
    schema: SchemaDetails,
    volume: VolumeDetails,
    freshness: FreshnessDetails,
    integrity: IntegrityDetails,
    contracts: ContractsDetails,
    cost: CostDetails,
  };

  const Renderer = renderers[finding.check_type] ?? FallbackDetails;

  return (
    <div className="py-2">
      <Renderer d={d} />
    </div>
  );
}
