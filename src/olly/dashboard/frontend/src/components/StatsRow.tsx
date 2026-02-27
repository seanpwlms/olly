interface StatsRowProps {
  children: React.ReactNode;
}

export function StatsRow({ children }: StatsRowProps) {
  return <div className="flex flex-wrap gap-4 mb-6">{children}</div>;
}
