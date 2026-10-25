import { CloseIcon } from "./CloseIcon";

export interface ActiveFilter {
  /** Field name shown before the value, e.g. "severity". */
  label: string;
  value: string;
  onRemove: () => void;
}

interface ActiveFiltersProps {
  filters: ActiveFilter[];
  onClearAll: () => void;
}

export function ActiveFilters({ filters, onClearAll }: ActiveFiltersProps) {
  if (filters.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-3">
      <span className="text-xs text-gray-500 dark:text-gray-400">Filtered by</span>
      {filters.map((f) => (
        <span
          key={`${f.label}:${f.value}`}
          className="inline-flex items-center gap-1 rounded-full border border-accent-200 dark:border-accent-900 bg-accent-50 dark:bg-accent-950/50 py-0.5 pl-2.5 pr-1 text-xs text-accent-700 dark:text-accent-300"
        >
          <span className="text-accent-600 dark:text-accent-400">{f.label}:</span>
          {f.value}
          <button
            onClick={f.onRemove}
            aria-label={`Remove ${f.label} filter`}
            className="rounded-full p-0.5 text-accent-600 dark:text-accent-400 hover:bg-accent-100 dark:hover:bg-accent-900 hover:text-accent-800 dark:hover:text-accent-200 transition-colors cursor-pointer"
          >
            <CloseIcon className="h-3.5 w-3.5" />
          </button>
        </span>
      ))}
      <button
        onClick={onClearAll}
        className="ml-1 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 underline underline-offset-2 transition-colors cursor-pointer"
      >
        Clear all
      </button>
    </div>
  );
}
