import { Link } from "@tanstack/react-router";

/** A `schema.table` identifier: monospace, and a link to the table page unless `plain`. */
export function TableRef({
  schema,
  table,
  plain = false,
  className = "",
}: {
  schema: string;
  table: string;
  plain?: boolean;
  className?: string;
}) {
  const name = (
    <>
      <span className="text-gray-500 dark:text-gray-400">{schema}.</span>
      {table}
    </>
  );
  if (plain) return <span className={`font-mono ${className}`}>{name}</span>;
  return (
    <Link
      to="/table/$schema/$table"
      params={{ schema, table }}
      onClick={(e) => e.stopPropagation()}
      className={`font-mono text-accent-700 hover:underline dark:text-accent-300 ${className}`}
    >
      {name}
    </Link>
  );
}
