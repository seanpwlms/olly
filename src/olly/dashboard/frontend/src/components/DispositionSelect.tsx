import { useState } from "react";
import { useSetDisposition } from "../hooks/queries";
import { DISPOSITIONS } from "../constants/dispositions";

interface DispositionSelectProps {
  findingId: number | null;
  currentDisposition: string;
}

export function DispositionSelect({ findingId, currentDisposition }: DispositionSelectProps) {
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState("");
  const [pendingDisposition, setPendingDisposition] = useState("");
  const mutation = useSetDisposition();

  if (findingId === null) return null;

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    if (value === currentDisposition) return;
    setPendingDisposition(value);
    setShowComment(true);
  };

  const handleSubmit = () => {
    mutation.mutate(
      { findingId, disposition: pendingDisposition, comment: comment.trim() },
      {
        onSuccess: () => {
          setShowComment(false);
          setComment("");
          setPendingDisposition("");
        },
      },
    );
  };

  const handleCancel = () => {
    setShowComment(false);
    setComment("");
    setPendingDisposition("");
  };

  const current = DISPOSITIONS.find((d) => d.value === currentDisposition) ?? DISPOSITIONS[0];

  if (showComment) {
    return (
      <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
        <input
          type="text"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Add a comment (optional)"
          className="text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 w-40"
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSubmit();
            if (e.key === "Escape") handleCancel();
          }}
          autoFocus
        />
        <button
          onClick={handleSubmit}
          disabled={mutation.isPending}
          className="text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {mutation.isPending ? "..." : "Save"}
        </button>
        <button
          onClick={handleCancel}
          className="text-xs px-2 py-1 rounded text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <select
      value={currentDisposition}
      onChange={handleChange}
      onClick={(e) => e.stopPropagation()}
      className={`text-xs font-medium rounded px-2 py-1 bg-transparent border border-gray-200 dark:border-gray-700 cursor-pointer ${current.color}`}
    >
      {DISPOSITIONS.map((d) => (
        <option key={d.value} value={d.value}>
          {d.label}
        </option>
      ))}
    </select>
  );
}
