import { useSearch, useNavigate } from "@tanstack/react-router";
import { useConnection } from "../hooks/useConnection";
import { useTables } from "../hooks/queries";
import { TablesTable } from "../components/TablesTable";
import { Pagination } from "../components/Pagination";
import { ErrorState } from "../components/ErrorState";
import { tablesRoute, type TablesSearch } from "../routeTree";

export function TablesPage() {
  const { connection } = useConnection();
  const searchParams = useSearch({ from: tablesRoute.id });
  const navigate = useNavigate({ from: tablesRoute.id });

  const search = searchParams.search ?? "";
  const sort = searchParams.sort ?? "table";
  const order = searchParams.order ?? "asc";
  const page = searchParams.page ?? 1;

  const setFilter = (updates: Partial<TablesSearch>) => {
    void navigate({
      search: (prev) => ({
        ...prev,
        ...updates,
        page: "page" in updates ? updates.page : 1,
      }),
    });
  };

  const handleSort = (column: string) => {
    if (sort === column) {
      setFilter({ sort: column, order: order === "asc" ? "desc" : "asc" });
    } else {
      setFilter({ sort: column, order: "asc" });
    }
  };

  const { data, isLoading, isError, refetch } = useTables({ connection, search, sort, order, page });

  if (isError) return <ErrorState message="Failed to load tables." onRetry={() => void refetch()} />;
  if (isLoading || !data) return <div className="text-center text-gray-500 py-8">Loading...</div>;

  return (
    <>
      <div className="flex justify-between items-center flex-wrap gap-2 mb-4">
        <h1 className="text-2xl font-bold text-gray-900">
          Tables <span className="font-normal text-gray-500 text-base">({data.total})</span>
        </h1>
        <input
          type="search"
          placeholder="Filter tables..."
          className="w-64 px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400 transition-colors"
          value={search}
          onChange={(e) => setFilter({ search: e.target.value || undefined })}
        />
      </div>
      <TablesTable
        tables={data.tables}
        sort={sort}
        order={order}
        onSort={handleSort}
      />
      <Pagination page={page} totalPages={data.total_pages} onPageChange={(p) => setFilter({ page: p > 1 ? p : undefined })} />
    </>
  );
}
