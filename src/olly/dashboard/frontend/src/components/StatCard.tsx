import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";

interface StatCardLink {
  to: string;
  search?: Record<string, string | number | undefined>;
}

interface StatCardProps {
  value: ReactNode;
  label: string;
  /** Colors the value only; severity is never repeated as a stripe or border. */
  variant?: "error" | "warning" | "ok";
  link?: StatCardLink;
  trend?: string;
  trendDirection?: "up" | "down" | "flat";
}

const valueStyles: Record<string, string> = {
  error: "text-red-600 dark:text-red-400",
  warning: "text-amber-700 dark:text-amber-400",
  ok: "text-emerald-700 dark:text-emerald-400",
};

const trendColors: Record<string, Record<string, string>> = {
  error: { up: "text-red-600 dark:text-red-400", down: "text-emerald-700 dark:text-emerald-400", flat: "text-gray-500 dark:text-gray-400" },
  warning: { up: "text-amber-700 dark:text-amber-400", down: "text-emerald-700 dark:text-emerald-400", flat: "text-gray-500 dark:text-gray-400" },
  ok: { up: "text-emerald-700 dark:text-emerald-400", down: "text-gray-500 dark:text-gray-400", flat: "text-gray-500 dark:text-gray-400" },
};

/** One cell of a StatsRow strip. Not a card: StatsRow draws the frame and dividers. */
export function StatCard({ value, label, variant, link, trend, trendDirection }: StatCardProps) {
  const valueColor = variant ? valueStyles[variant] : "text-gray-900 dark:text-gray-100";
  const trendColor =
    trend && trendDirection && variant
      ? trendColors[variant]?.[trendDirection] ?? "text-gray-500 dark:text-gray-400"
      : "text-gray-500 dark:text-gray-400";

  const content = (
    <>
      <div className="text-sm text-gray-500 dark:text-gray-400">{label}</div>
      <div className={`mt-0.5 text-2xl font-semibold ${valueColor}`}>{value}</div>
      {trend && <div className={`mt-0.5 text-xs ${trendColor}`}>{trend}</div>}
    </>
  );

  const cell = "block bg-white dark:bg-gray-900 px-4 py-3";

  if (link) {
    return (
      <Link
        to={link.to}
        search={link.search}
        className={`${cell} no-underline text-inherit hover:bg-gray-50 dark:hover:bg-gray-800/60 transition-colors`}
      >
        {content}
      </Link>
    );
  }

  return <div className={cell}>{content}</div>;
}
