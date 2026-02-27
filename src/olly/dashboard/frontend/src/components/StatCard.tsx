import { Link } from "@tanstack/react-router";

interface StatCardLink {
  to: string;
  search?: Record<string, string | number | undefined>;
}

interface StatCardProps {
  value: string | number;
  label: string;
  variant?: "error" | "warning" | "ok";
  link?: StatCardLink;
  trend?: string;
  trendDirection?: "up" | "down" | "flat";
  size?: "default" | "hero";
}

const accentStyles: Record<string, string> = {
  error: "border-l-4 border-l-red-400",
  warning: "border-l-4 border-l-amber-400",
  ok: "border-l-4 border-l-emerald-400",
};

const valueStyles: Record<string, string> = {
  error: "text-red-600 dark:text-red-400",
  warning: "text-amber-600 dark:text-amber-400",
  ok: "text-emerald-600 dark:text-emerald-400",
};

const trendColors: Record<string, Record<string, string>> = {
  error: { up: "text-red-500", down: "text-emerald-500", flat: "text-gray-400" },
  warning: { up: "text-amber-500", down: "text-emerald-500", flat: "text-gray-400" },
  ok: { up: "text-emerald-500", down: "text-gray-400", flat: "text-gray-400" },
};

export function StatCard({ value, label, variant, link, trend, trendDirection, size = "default" }: StatCardProps) {
  const accent = variant ? accentStyles[variant] : "";
  const valueColor = variant ? valueStyles[variant] : "text-gray-900 dark:text-white";
  const trendColor =
    trend && trendDirection && variant
      ? trendColors[variant]?.[trendDirection] ?? "text-gray-400"
      : "text-gray-400";

  const isHero = size === "hero";

  const content = (
    <div
      className={`bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm hover:shadow-md transition-shadow ${accent} ${isHero ? "px-6 py-5" : "px-5 py-4"} ${isHero ? "" : "flex-1 min-w-[140px]"}`}
    >
      <div className={`font-bold ${valueColor} ${isHero ? "text-4xl" : "text-2xl"}`}>{value}</div>
      <div className={`text-gray-500 dark:text-gray-400 uppercase tracking-wide mt-1 ${isHero ? "text-sm" : "text-xs"}`}>{label}</div>
      {trend && (
        <div className={`mt-1 ${trendColor} ${isHero ? "text-sm" : "text-xs"}`}>{trend}</div>
      )}
    </div>
  );

  if (link) {
    return (
      <Link
        to={link.to}
        search={link.search}
        className={`no-underline text-inherit block ${isHero ? "" : "flex-1 min-w-[140px]"}`}
      >
        {content}
      </Link>
    );
  }

  return content;
}
