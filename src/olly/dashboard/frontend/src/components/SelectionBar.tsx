import { useEffect, useRef, useState } from "react";
import { useBulkDisposition } from "../hooks/queries";
import { DISPOSITIONS } from "../constants/dispositions";

interface SelectionBarProps {
  /** Selectable finding ids on the current page. */
  pageIds: number[];
  /** Every finding id matching the active filters, across all pages. */
  allIds: number[];
  selected: Set<number>;
  onChange: (next: Set<number>) => void;
}

/** Checkbox that shows a dash when only some rows are selected. */
function TriStateCheckbox({
  checked,
  indeterminate,
  onChange,
  label,
}: {
  checked: boolean;
  indeterminate: boolean;
  onChange: () => void;
  label: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return (
    <input
      ref={ref}
      type="checkbox"
      checked={checked}
      onChange={onChange}
      aria-label={label}
      className="rounded border-gray-300 dark:border-gray-600 cursor-pointer"
    />
  );
}

export function SelectionBar({ pageIds, allIds, selected, onChange }: SelectionBarProps) {
  const [disposition, setDisposition] = useState("completed");
  const [comment, setComment] = useState("");
  const mutation = useBulkDisposition();

  const count = selected.size;
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  const allMatchingSelected = allIds.length > 0 && count >= allIds.length;
  // Only worth offering "select all matching" when it reaches beyond this page.
  const canEscalate = allPageSelected && !allMatchingSelected && allIds.length > pageIds.length;

  const togglePage = () =>
    onChange(allPageSelected ? new Set() : new Set([...selected, ...pageIds]));

  const apply = () => {
    mutation.mutate(
      { findingIds: Array.from(selected), disposition, comment: comment.trim() },
      {
        onSuccess: () => {
          onChange(new Set());
          setComment("");
        },
      },
    );
  };

  const active = count > 0;

  return (
    <div
      className={`sticky top-0 z-10 rounded-lg border p-3 mb-2 flex items-center gap-3 flex-wrap transition-colors ${
        active
          ? "bg-accent-50 dark:bg-accent-900/30 border-accent-200 dark:border-accent-800"
          : "bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-800"
      }`}
    >
      <TriStateCheckbox
        checked={allPageSelected}
        indeterminate={count > 0 && !allPageSelected}
        onChange={togglePage}
        label={allPageSelected ? "Clear selection" : "Select all on this page"}
      />
      <span
        className={`text-sm font-medium ${
          active
            ? "text-accent-800 dark:text-accent-200"
            : "text-gray-600 dark:text-gray-400"
        }`}
      >
        {active ? `${count} selected` : "Select all"}
      </span>

      {canEscalate && (
        <button
          onClick={() => onChange(new Set(allIds))}
          className="text-sm text-accent-600 dark:text-accent-400 hover:underline cursor-pointer"
        >
          Select all {allIds.length} matching
        </button>
      )}
      {allMatchingSelected && allIds.length > pageIds.length && (
        <span className="text-sm text-accent-700 dark:text-accent-300">
          All {allIds.length} matching findings selected
        </span>
      )}

      {active && (
        <>
          <span className="flex-1" />
          <select
            value={disposition}
            onChange={(e) => setDisposition(e.target.value)}
            aria-label="Status to apply"
            className="text-xs font-medium rounded px-2 py-1.5 border border-accent-200 dark:border-accent-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
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
            className="text-xs border border-accent-200 dark:border-accent-700 rounded px-2 py-1.5 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 w-40"
          />
          <button
            onClick={apply}
            disabled={mutation.isPending}
            className="text-xs px-3 py-1.5 rounded bg-accent-600 text-white hover:bg-accent-700 disabled:opacity-50 font-medium cursor-pointer"
          >
            {mutation.isPending ? "Applying…" : "Apply"}
          </button>
          <button
            onClick={() => onChange(new Set())}
            className="text-xs px-2 py-1.5 rounded text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 cursor-pointer"
          >
            Clear
          </button>
        </>
      )}
    </div>
  );
}
