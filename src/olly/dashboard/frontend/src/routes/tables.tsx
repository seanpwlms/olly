import { useState } from "react";
import { useConnection } from "../hooks/useConnection";
import { useTables } from "../hooks/queries";
import { TablesTable } from "../components/TablesTable";
import { Pagination } from "../components/Pagination";

export function TablesPage() {
  const { connection } = useConnection();
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("table");
  const [order, setOrder] = useState("asc");
  const [page, setPage] = useState(1);

  const { data, isLoading } = useTables({ connection, search, sort, order, page });

  const handleSort = (column: string) => {
    if (sort === column) {
      setOrder(order === "asc" ? "desc" : "asc");
    } else {
      setSort(column);
      setOrder("asc");
    }
    setPage(1);
  };

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
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
      </div>
      <TablesTable
        tables={data.tables}
        sort={sort}
        order={order}
        onSort={handleSort}
      />
      <Pagination page={page} totalPages={data.total_pages} onPageChange={setPage} />
    </>
  );
}
