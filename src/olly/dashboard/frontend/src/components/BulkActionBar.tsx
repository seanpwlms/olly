import { useState } from "react";
import { useBulkDisposition } from "../hooks/queries";
import { DISPOSITIONS } from "../constants/dispositions";

interface BulkActionBarProps {
  selectedIds: Set<number>;
  onClear: () => void;
}

export function BulkActionBar({ selectedIds, onClear }: BulkActionBarProps) {
  const [disposition, setDisposition] = useState("completed");
  const [comment, setComment] = useState("");
  const mutation = useBulkDisposition();

  if (selectedIds.size === 0) return null;

  const handleApply = () => {
    mutation.mutate(
      { findingIds: Array.from(selectedIds), disposition, comment: comment.trim() },
      {
        onSuccess: () => {
          onClear();
          setComment("");
        },
      },
    );
  };

  return (
    <div className="sticky top-0 z-10 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg p-3 mb-2 flex items-center gap-3 flex-wrap">
      <span className="text-sm font-medium text-blue-800 dark:text-blue-200">
        {selectedIds.size} selected
      </span>
      <select
        value={disposition}
        onChange={(e) => setDisposition(e.target.value)}
        className="text-xs font-medium rounded px-2 py-1.5 border border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
      >
        {DISPOSITIONS.map((d) => (
          <option key={d.value} value={d.value}>{d.label}</option>
        ))}
      </select>
      <input
        type="text"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Comment (optional)"
        className="text-xs border border-blue-200 dark:border-blue-700 rounded px-2 py-1.5 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 w-40"
      />
      <button
        onClick={handleApply}
        disabled={mutation.isPending}
        className="text-xs px-3 py-1.5 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 font-medium"
      >
        {mutation.isPending ? "Applying..." : "Apply"}
      </button>
      <button
        onClick={onClear}
        className="text-xs px-2 py-1.5 rounded text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
      >
        Clear
      </button>
    </div>
  );
}
