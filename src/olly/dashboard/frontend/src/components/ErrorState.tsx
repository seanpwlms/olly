interface ErrorStateProps {
  message: string;
  onRetry: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="text-center py-8">
      <p className="text-red-600 font-medium">{message}</p>
      <button
        className="mt-2 text-sm text-blue-600 hover:underline"
        onClick={onRetry}
      >
        Retry
      </button>
    </div>
  );
}
