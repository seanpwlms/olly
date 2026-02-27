interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, totalPages, onPageChange }: PaginationProps) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-4 py-3">
      {page > 1 && (
        <button
          className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors cursor-pointer"
          onClick={() => onPageChange(page - 1)}
        >
          Previous
        </button>
      )}
      <span className="text-sm text-gray-500 dark:text-gray-400">
        Page {page} of {totalPages}
      </span>
      {page < totalPages && (
        <button
          className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors cursor-pointer"
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </button>
      )}
    </div>
  );
}
