interface BadgeProps {
  type: string;
  children: React.ReactNode;
}

const badgeStyles: Record<string, string> = {
  error: "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
  warning: "bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-400",
  ok: "bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400",
  pass: "bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400",
  unused: "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
  stale: "bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-400",
  added: "bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400",
  removed: "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
  not_started: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  no_action: "bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400",
  in_progress: "bg-purple-50 text-purple-600 dark:bg-purple-950 dark:text-purple-400",
  completed: "bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400",
};

export function Badge({ type, children }: BadgeProps) {
  const colors = badgeStyles[type] ?? "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${colors}`}
    >
      {children}
    </span>
  );
}
