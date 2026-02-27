interface BadgeProps {
  type: string;
  children: React.ReactNode;
}

const badgeStyles: Record<string, string> = {
  error: "bg-red-50 text-red-600",
  warning: "bg-amber-50 text-amber-600",
  ok: "bg-emerald-50 text-emerald-600",
  pass: "bg-emerald-50 text-emerald-600",
  unused: "bg-red-50 text-red-600",
  stale: "bg-amber-50 text-amber-600",
  added: "bg-emerald-50 text-emerald-600",
  removed: "bg-red-50 text-red-600",
};

export function Badge({ type, children }: BadgeProps) {
  const colors = badgeStyles[type] ?? "bg-gray-100 text-gray-600";
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${colors}`}
    >
      {children}
    </span>
  );
}
