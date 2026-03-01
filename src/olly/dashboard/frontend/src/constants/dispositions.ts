export const DISPOSITIONS = [
  { value: "not_started", label: "Not Started", color: "text-gray-600 dark:text-gray-400" },
  { value: "in_progress", label: "In Progress", color: "text-purple-600 dark:text-purple-400" },
  { value: "no_action", label: "No Action", color: "text-blue-600 dark:text-blue-400" },
  { value: "completed", label: "Completed", color: "text-emerald-600 dark:text-emerald-400" },
] as const;

export const DISPOSITION_LABELS: Record<string, string> = Object.fromEntries(
  DISPOSITIONS.map((d) => [d.value, d.label]),
);
