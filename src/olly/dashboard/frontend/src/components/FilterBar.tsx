interface FilterOption {
  value: string;
  label: string;
}

interface FilterBarProps {
  filters: {
    name: string;
    value: string;
    options: FilterOption[];
    placeholder: string;
    onChange: (value: string) => void;
  }[];
  search?: {
    value: string;
    placeholder: string;
    onChange: (value: string) => void;
  };
  children?: React.ReactNode;
}

export function FilterBar({ filters, search, children }: FilterBarProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {search && (
        <input
          type="search"
          value={search.value}
          placeholder={search.placeholder}
          className="min-w-[180px] px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400 transition-colors"
          onChange={(e) => search.onChange(e.target.value)}
        />
      )}
      {filters.map((f) => (
        <select
          key={f.name}
          value={f.value}
          className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400 transition-colors"
          onChange={(e) => f.onChange(e.target.value)}
        >
          <option value="">{f.placeholder}</option>
          {f.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ))}
      {children}
    </div>
  );
}
