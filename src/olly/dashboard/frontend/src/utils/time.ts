/** Hours after which the last check run is considered stale. */
export const STALE_CHECK_HOURS = 24;

const EM_DASH = "—";

export function timeAgo(dateStr: string): string {
  if (!dateStr) return "";
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/** "2026-09-11T14:03:22" -> "2026-09-11 14:03". */
export function formatTimestamp(dateStr: string | null | undefined): string {
  if (!dateStr) return EM_DASH;
  return dateStr.slice(0, 16).replace("T", " ");
}

/** "2026-09-11T14:03:22" -> "2026-09-11". */
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return EM_DASH;
  return dateStr.slice(0, 10);
}

/** Whole hours elapsed since `dateStr`, or null if it is missing/unparseable. */
export function hoursSince(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null;
  const ms = new Date(dateStr).getTime();
  if (Number.isNaN(ms)) return null;
  return Math.floor((Date.now() - ms) / 3_600_000);
}

/** True when the last check ran long enough ago that its numbers are suspect. */
export function isCheckStale(dateStr: string | null | undefined): boolean {
  const hours = hoursSince(dateStr);
  return hours !== null && hours >= STALE_CHECK_HOURS;
}
