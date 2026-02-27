interface EmptyStateProps {
  message: string;
  variant?: "empty" | "healthy";
}

export function EmptyState({ message, variant = "empty" }: EmptyStateProps) {
  if (variant === "healthy") {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950 px-5 py-4">
        <svg className="h-5 w-5 text-emerald-600 dark:text-emerald-400 shrink-0" viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
        </svg>
        <span className="text-sm font-medium text-emerald-800 dark:text-emerald-300">{message}</span>
      </div>
    );
  }

  return <p className="text-center text-gray-400 py-8">{message}</p>;
}
