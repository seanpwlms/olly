import { useDispositionHistory } from "../hooks/queries";
import { Badge } from "./Badge";
import { timeAgo } from "../utils/timeAgo";
import { DISPOSITION_LABELS } from "../constants/dispositions";

interface DispositionHistoryProps {
  findingId: number | null;
}

export function DispositionHistory({ findingId }: DispositionHistoryProps) {
  const { data, isLoading } = useDispositionHistory(findingId);

  if (isLoading) {
    return <p className="text-xs text-gray-400 py-2">Loading history...</p>;
  }

  if (!data || data.history.length === 0) {
    return <p className="text-xs text-gray-400 py-2">No disposition changes yet</p>;
  }

  return (
    <div className="space-y-2 py-2">
      {data.history.map((event) => (
        <div key={event.id} className="flex items-start gap-2 text-xs">
          <div className="w-1.5 h-1.5 rounded-full bg-gray-400 dark:bg-gray-500 mt-1.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <Badge type={event.disposition}>
                {DISPOSITION_LABELS[event.disposition] ?? event.disposition}
              </Badge>
              <span className="text-gray-400">{timeAgo(event.created_at)}</span>
            </div>
            {event.comment && (
              <p className="text-gray-500 dark:text-gray-400 mt-0.5 truncate">
                {event.comment}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
