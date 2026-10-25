function SkeletonBox({ className = "", style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={`animate-pulse bg-gray-200 dark:bg-gray-800 rounded ${className}`} style={style} />;
}

/** Mirrors StatsRow + StatCard. */
export function SkeletonStatCards({ count = 3 }: { count?: number }) {
  return (
    <div className="mb-6 grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-px overflow-hidden rounded-lg border border-gray-200 bg-gray-200 dark:border-gray-800 dark:bg-gray-800">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="bg-white dark:bg-gray-900 px-4 py-3">
          <SkeletonBox className="h-3.5 w-20 mb-2" />
          <SkeletonBox className="h-7 w-14" />
        </div>
      ))}
    </div>
  );
}

/** Mirrors DataTable: no card, a header rule and row dividers. */
export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="w-full mb-6">
      <div className="border-b border-gray-200 dark:border-gray-800 px-3 py-2.5 flex gap-4">
        {Array.from({ length: cols }, (_, i) => (
          <SkeletonBox key={i} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="px-3 py-3 border-b border-gray-100 dark:border-gray-800/70 flex gap-4">
          {Array.from({ length: cols }, (_, j) => (
            <SkeletonBox key={j} className="h-4 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonChart({ height = 240 }: { height?: number }) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4 mb-6">
      <SkeletonBox className="w-full" style={{ height }} />
    </div>
  );
}
