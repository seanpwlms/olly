interface NotConfiguredProps {
  /** What the feature does, in one line. */
  description: string;
  /** The `olly.toml` block the user needs to add to enable it. */
  snippet: string;
}

export function NotConfigured({ description, snippet }: NotConfiguredProps) {
  return (
    <div className="rounded-lg border border-dashed border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-8">
      <div className="mx-auto max-w-lg text-center">
        <svg
          className="mx-auto h-8 w-8 text-gray-500 dark:text-gray-600"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M12 9v4m0 4h.01M12 3a9 9 0 100 18 9 9 0 000-18z" />
        </svg>
        <h3 className="mt-3 text-sm font-semibold text-gray-800 dark:text-gray-200">
          Not configured
        </h3>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{description}</p>
        <pre className="mt-4 overflow-x-auto rounded-lg bg-gray-900 dark:bg-gray-950 border border-gray-800 px-4 py-3 text-left text-xs leading-relaxed text-gray-200">
          <code>{snippet}</code>
        </pre>
        <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
          Add this to <code>olly.toml</code>, then run{" "}
          <code className="text-gray-500 dark:text-gray-400">olly check</code>.
        </p>
      </div>
    </div>
  );
}
