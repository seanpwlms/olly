interface NavIconProps {
  name: string;
  className?: string;
}

// Single-path 24x24 stroke icons, one per nav destination.
const paths: Record<string, string> = {
  overview: "M3 12l9-9 9 9M5 10v10h14V10",
  findings: "M12 9v4m0 4h.01M10.3 3.9L2.4 17a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z",
  tables: "M3 5h18v14H3zM3 10h18M9 10v9",
  contracts: "M9 12l2 2 4-4M7 3h10a2 2 0 012 2v14a2 2 0 01-2 2H7a2 2 0 01-2-2V5a2 2 0 012-2z",
  integrity: "M8 7h8m-8 5h8m-8 5h4M4 4v16M20 4v16",
  usage: "M3 20h18M7 20v-7M12 20V7M17 20v-4",
  dbt: "M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3zM12 12l8-4.5M12 12v9M12 12L4 7.5",
};

export function NavIcon({ name, className = "" }: NavIconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] ?? paths.findings} />
    </svg>
  );
}
