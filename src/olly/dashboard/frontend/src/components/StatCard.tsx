interface StatCardProps {
  value: string | number;
  label: string;
  variant?: "error" | "warning" | "ok";
  href?: string;
  trend?: string;
  trendDirection?: "up" | "down" | "flat";
}

const accentStyles: Record<string, string> = {
  error: "border-l-4 border-l-red-400",
  warning: "border-l-4 border-l-amber-400",
  ok: "border-l-4 border-l-emerald-400",
};

const valueStyles: Record<string, string> = {
  error: "text-red-600",
  warning: "text-amber-600",
  ok: "text-emerald-600",
};

const trendColors: Record<string, Record<string, string>> = {
  error: { up: "text-red-500", down: "text-emerald-500", flat: "text-gray-400" },
  warning: { up: "text-amber-500", down: "text-emerald-500", flat: "text-gray-400" },
  ok: { up: "text-emerald-500", down: "text-gray-400", flat: "text-gray-400" },
};

export function StatCard({ value, label, variant, href, trend, trendDirection }: StatCardProps) {
  const accent = variant ? accentStyles[variant] : "";
  const valueColor = variant ? valueStyles[variant] : "text-gray-900";
  const trendColor =
    trend && trendDirection && variant
      ? trendColors[variant]?.[trendDirection] ?? "text-gray-400"
      : "text-gray-400";

  const content = (
    <div
      className={`bg-white rounded-lg border border-gray-200 shadow-sm px-5 py-4 flex-1 min-w-[140px] hover:shadow-md transition-shadow ${accent}`}
    >
      <div className={`text-2xl font-bold ${valueColor}`}>{value}</div>
      <div className="text-xs text-gray-500 uppercase tracking-wide mt-1">{label}</div>
      {trend && (
        <div className={`text-xs mt-1 ${trendColor}`}>{trend}</div>
      )}
    </div>
  );

  if (href) {
    return (
      <a href={href} className="no-underline text-inherit block flex-1 min-w-[140px]">
        {content}
      </a>
    );
  }

  return content;
}
