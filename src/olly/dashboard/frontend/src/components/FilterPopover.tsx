import { useEffect, useRef, useState, type ReactNode } from "react";

interface FilterPopoverProps {
  /** Number of filters currently set, shown as a badge on the trigger. */
  activeCount: number;
  children: ReactNode;
}

export function FilterPopover({ activeCount, children }: FilterPopoverProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm transition-colors cursor-pointer ${
          activeCount > 0
            ? "border-accent-400 text-accent-600 dark:text-accent-400 bg-accent-50 dark:bg-accent-950/40"
            : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-600 dark:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600"
        }`}
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M4 5h16l-6.5 7.5V19l-3 1.5v-8L4 5z" />
        </svg>
        Filters
        {activeCount > 0 && (
          <span className="rounded-full bg-accent-600 px-1.5 text-xs font-semibold leading-4 text-white">
            {activeCount}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1.5 w-64 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-3 shadow-lg space-y-3">
          {children}
        </div>
      )}
    </div>
  );
}

interface FilterSelectProps {
  label: string;
  value: string;
  options: string[];
  allLabel: string;
  format?: (value: string) => string;
  onChange: (value: string) => void;
}

export function FilterSelect({
  label,
  value,
  options,
  allLabel,
  format,
  onChange,
}: FilterSelectProps) {
  return (
    <label className="block">
      <span className="block pb-1 text-xs font-semibold text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <select
        className="w-full px-2.5 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-accent-500/40 focus:border-accent-400"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{allLabel}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {format ? format(o) : o}
          </option>
        ))}
      </select>
    </label>
  );
}
