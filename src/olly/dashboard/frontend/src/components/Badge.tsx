interface BadgeProps {
  type: string;
  children: React.ReactNode;
}

const RED = "bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300";
const AMBER = "bg-amber-50 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300";
const GREEN = "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300";
const NEUTRAL = "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";

const badgeStyles: Record<string, string> = {
  error: RED,
  warning: AMBER,
  ok: GREEN,
  pass: GREEN,
  unused: RED,
  stale: AMBER,
  added: GREEN,
  removed: RED,
  not_started: NEUTRAL,
  no_action: NEUTRAL,
  in_progress: "bg-accent-50 text-accent-700 dark:bg-accent-950 dark:text-accent-300",
  completed: GREEN,
};

export function Badge({ type, children }: BadgeProps) {
  const colors = badgeStyles[type] ?? NEUTRAL;
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium leading-none ${colors}`}>
      {children}
    </span>
  );
}
