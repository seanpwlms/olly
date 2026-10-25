export const DISPOSITIONS = [
  { value: "not_started", label: "Not started", color: "text-gray-600 dark:text-gray-400" },
  { value: "in_progress", label: "In progress", color: "text-accent-600 dark:text-accent-400" },
  { value: "no_action", label: "No action", color: "text-gray-500 dark:text-gray-400" },
  { value: "completed", label: "Completed", color: "text-emerald-700 dark:text-emerald-400" },
] as const;

export const DISPOSITION_LABELS: Record<string, string> = Object.fromEntries(
  DISPOSITIONS.map((d) => [d.value, d.label]),
);
