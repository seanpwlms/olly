interface StatsRowProps {
  children: React.ReactNode;
}

/**
 * A single framed strip of StatCards separated by hairlines. The 1px gap over a
 * border-colored background draws the dividers, so they stay correct when the
 * strip wraps onto several rows.
 */
export function StatsRow({ children }: StatsRowProps) {
  return (
    <div className="mb-6 grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-px overflow-hidden rounded-lg border border-gray-200 bg-gray-200 dark:border-gray-800 dark:bg-gray-800">
      {children}
    </div>
  );
}
