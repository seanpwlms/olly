import { formatTimestamp, timeAgo } from "../utils/time";

/** "3h ago", with the absolute time in a tooltip. Use in lists; detail views show formatTimestamp. */
export function RelativeTime({ value, className = "" }: { value: string; className?: string }) {
  return (
    <time dateTime={value} title={formatTimestamp(value)} className={className}>
      {timeAgo(value)}
    </time>
  );
}
