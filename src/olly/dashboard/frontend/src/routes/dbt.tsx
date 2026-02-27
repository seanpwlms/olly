import { DbtContent } from "../components/DbtContent";

export function DbtPage() {
  return (
    <>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">dbt Run Results</h1>
      <DbtContent />
    </>
  );
}
