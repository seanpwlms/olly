import { useRef, useEffect, useState } from "react";
import { useDbtPreviousSql } from "../hooks/queries";

interface CompiledSqlModalProps {
  sql: string;
  nodeId: string;
  dbtRunId: number | null;
  onClose: () => void;
}

type DiffLine = { type: "same" | "added" | "removed"; text: string };

function computeDiff(oldText: string, newText: string): DiffLine[] {
  const oldLines = oldText.split("\n");
  const newLines = newText.split("\n");
  const result: DiffLine[] = [];

  let oi = 0;
  let ni = 0;
  while (oi < oldLines.length && ni < newLines.length) {
    const oldLine = oldLines[oi]!;
    const newLine = newLines[ni]!;
    if (oldLine === newLine) {
      result.push({ type: "same", text: oldLine });
      oi++;
      ni++;
    } else {
      // Look ahead for matches
      let foundInNew = -1;
      for (let j = ni + 1; j < Math.min(ni + 10, newLines.length); j++) {
        if (newLines[j] === oldLine) { foundInNew = j; break; }
      }
      let foundInOld = -1;
      for (let j = oi + 1; j < Math.min(oi + 10, oldLines.length); j++) {
        if (oldLines[j] === newLine) { foundInOld = j; break; }
      }

      if (foundInNew >= 0 && (foundInOld < 0 || foundInNew - ni <= foundInOld - oi)) {
        for (let j = ni; j < foundInNew; j++) result.push({ type: "added", text: newLines[j]! });
        ni = foundInNew;
      } else if (foundInOld >= 0) {
        for (let j = oi; j < foundInOld; j++) result.push({ type: "removed", text: oldLines[j]! });
        oi = foundInOld;
      } else {
        result.push({ type: "removed", text: oldLine });
        result.push({ type: "added", text: newLine });
        oi++;
        ni++;
      }
    }
  }
  for (; oi < oldLines.length; oi++) result.push({ type: "removed", text: oldLines[oi]! });
  for (; ni < newLines.length; ni++) result.push({ type: "added", text: newLines[ni]! });
  return result;
}

export function CompiledSqlModal({ sql, nodeId, dbtRunId, onClose }: CompiledSqlModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [showDiff, setShowDiff] = useState(false);
  const { data: prevData, isLoading } = useDbtPreviousSql(nodeId, dbtRunId);

  useEffect(() => {
    dialogRef.current?.showModal();
  }, []);

  const previousSql = prevData?.previous_sql ?? null;
  const hasPrevious = previousSql !== null;
  const sqlChanged = hasPrevious && previousSql !== sql;

  const diffLines = showDiff && sqlChanged ? computeDiff(previousSql, sql) : null;

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
        <div className="flex items-center gap-3">
          {!isLoading && hasPrevious && (
            <div className="flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden">
              <button
                onClick={() => setShowDiff(false)}
                className={`px-2.5 py-1 text-xs font-medium transition-colors ${
                  !showDiff
                    ? "bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900"
                    : "bg-white dark:bg-gray-800 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                }`}
              >
                Current
              </button>
              <button
                onClick={() => setShowDiff(true)}
                className={`px-2.5 py-1 text-xs font-medium transition-colors ${
                  showDiff
                    ? "bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900"
                    : "bg-white dark:bg-gray-800 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                }`}
              >
                Diff
              </button>
            </div>
          )}
          <button
            className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 text-xl leading-none transition-colors"
            onClick={onClose}
          >
            &times;
          </button>
        </div>
      </div>
      {showDiff && diffLines ? (
        <pre className="m-0 p-5 bg-gray-900 text-gray-200 overflow-x-auto text-sm whitespace-pre-wrap rounded-b-xl max-h-[70vh] overflow-y-auto">
          <code>
            {sqlChanged ? diffLines.map((line, i) => (
              <div
                key={i}
                className={
                  line.type === "added"
                    ? "bg-green-900/40 text-green-300"
                    : line.type === "removed"
                    ? "bg-red-900/40 text-red-300"
                    : ""
                }
              >
                <span className="select-none text-gray-500 mr-2">
                  {line.type === "added" ? "+" : line.type === "removed" ? "-" : " "}
                </span>
                {line.text}
              </div>
            )) : (
              <span className="text-gray-400">No changes from previous run</span>
            )}
          </code>
        </pre>
      ) : showDiff && hasPrevious && !sqlChanged ? (
        <pre className="m-0 p-5 bg-gray-900 text-gray-200 overflow-x-auto text-sm whitespace-pre-wrap rounded-b-xl max-h-[70vh] overflow-y-auto">
          <code>
            <span className="text-gray-400">No changes from previous run</span>
          </code>
        </pre>
      ) : (
        <pre className="m-0 p-5 bg-gray-900 text-gray-200 overflow-x-auto text-sm whitespace-pre-wrap rounded-b-xl max-h-[70vh] overflow-y-auto">
          <code>{sql}</code>
        </pre>
      )}
    </dialog>
  );
}
