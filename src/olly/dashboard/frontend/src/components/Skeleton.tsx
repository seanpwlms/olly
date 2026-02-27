function SkeletonBox({ className = "", style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={`animate-pulse bg-gray-200 dark:bg-gray-800 rounded ${className}`} style={style} />;
}

export function SkeletonStatCards({ count = 3 }: { count?: number }) {
  return (
    <div className="flex flex-wrap gap-4 mb-6">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="flex-1 min-w-[140px] bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm px-5 py-4">
          <SkeletonBox className="h-7 w-16 mb-2" />
          <SkeletonBox className="h-3 w-20" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="w-full bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden mb-6">
      <div className="bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 py-3 flex gap-4">
        {Array.from({ length: cols }, (_, i) => (
          <SkeletonBox key={i} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="px-4 py-3 border-b border-gray-100 dark:border-gray-800 flex gap-4">
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
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-sm p-4 mb-6">
      <SkeletonBox className="w-full" style={{ height }} />
    </div>
  );
}
