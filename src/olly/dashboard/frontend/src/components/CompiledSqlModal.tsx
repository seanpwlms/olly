import { useRef, useEffect } from "react";

interface CompiledSqlModalProps {
  sql: string;
  nodeId: string;
  onClose: () => void;
}

export function CompiledSqlModal({ sql, nodeId, onClose }: CompiledSqlModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    dialogRef.current?.showModal();
  }, []);

  return (
    <dialog
      ref={dialogRef}
      className="border-none rounded-xl p-0 max-w-2xl w-[90vw] shadow-2xl backdrop:bg-black/50 backdrop:backdrop-blur-sm"
      onClose={onClose}
    >
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800">
        <span className="font-semibold text-sm text-gray-800 dark:text-gray-200">
          Compiled SQL &mdash; {nodeId}
        </span>
        <button
          className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 text-xl leading-none transition-colors"
          onClick={onClose}
        >
          &times;
        </button>
      </div>
      <pre className="m-0 p-5 bg-gray-900 text-gray-200 overflow-x-auto text-sm whitespace-pre-wrap rounded-b-xl">
        <code>{sql}</code>
      </pre>
    </dialog>
  );
}
