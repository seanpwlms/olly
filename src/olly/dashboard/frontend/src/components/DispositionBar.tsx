import { Link } from "@tanstack/react-router";
import type { DispositionCounts } from "../types";

const DISPOSITION_SEGMENTS = [
  { key: "not_started" as const, label: "Not Started", color: "bg-gray-400 dark:bg-gray-500", text: "text-gray-600 dark:text-gray-400" },
  { key: "in_progress" as const, label: "In Progress", color: "bg-purple-500 dark:bg-purple-400", text: "text-purple-600 dark:text-purple-400" },
  { key: "no_action" as const, label: "No Action", color: "bg-blue-400 dark:bg-blue-500", text: "text-blue-600 dark:text-blue-400" },
  { key: "completed" as const, label: "Completed", color: "bg-emerald-500 dark:bg-emerald-400", text: "text-emerald-600 dark:text-emerald-400" },
] as const;

export function DispositionBar({ counts }: { counts: DispositionCounts }) {
  const total = counts.not_started + counts.in_progress + counts.no_action + counts.completed;
  if (total === 0) return null;
  const acted = counts.in_progress + counts.no_action + counts.completed;

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {acted} of {total} findings addressed
        </span>
        <span className="text-xs text-gray-400">
          ({total - acted} need attention)
        </span>
      </div>
      <div className="flex h-3 rounded-full overflow-hidden bg-gray-100 dark:bg-gray-800 mb-3">
        {DISPOSITION_SEGMENTS.map((seg) => {
          const count = counts[seg.key];
          if (count === 0) return null;
          const pct = (count / total) * 100;
          return (
            <div
              key={seg.key}
              className={`${seg.color} transition-all`}
              style={{ width: `${pct}%` }}
              title={`${seg.label}: ${count}`}
            />
          );
        })}
      </div>
      <div className="flex flex-wrap gap-4">
        {DISPOSITION_SEGMENTS.map((seg) => {
          const count = counts[seg.key];
          return (
            <Link
              key={seg.key}
              to="/findings"
              search={{ disposition: seg.key }}
              className="flex items-center gap-1.5 no-underline"
            >
              <div className={`w-2.5 h-2.5 rounded-full ${seg.color}`} />
              <span className={`text-xs font-medium ${seg.text}`}>
                {seg.label}: {count}
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
