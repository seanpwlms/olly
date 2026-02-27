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
          className="px-3 py-1.5 border border-gray-200 rounded-lg bg-white text-sm hover:bg-gray-50 transition-colors cursor-pointer"
          onClick={() => onPageChange(page - 1)}
        >
          Previous
        </button>
      )}
      <span className="text-sm text-gray-500">
        Page {page} of {totalPages}
      </span>
      {page < totalPages && (
        <button
          className="px-3 py-1.5 border border-gray-200 rounded-lg bg-white text-sm hover:bg-gray-50 transition-colors cursor-pointer"
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </button>
      )}
    </div>
  );
}
