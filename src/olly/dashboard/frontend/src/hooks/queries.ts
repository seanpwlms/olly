import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchApi, postApi } from "../api";
import type {
  ConnectionsResponse,
  OverviewResponse,
  FindingsResponse,
  TablesResponse,
  TableDetailResponse,
  UsageResponse,
  DbtResponse,
} from "../types";

export function useConnections() {
  return useQuery({
    queryKey: ["connections"],
    queryFn: () => fetchApi<ConnectionsResponse>("/api/connections"),
  });
}

export function useOverview(connection: string) {
  return useQuery({
    queryKey: ["overview", connection],
    queryFn: () =>
      fetchApi<OverviewResponse>("/api/overview", { connection }),
  });
}

export function useFindings(params: {
  connection: string;
  check_type?: string;
  severity?: string;
  schema?: string;
  q?: string;
  page?: number;
}) {
  return useQuery({
    queryKey: ["findings", params],
    queryFn: () =>
      fetchApi<FindingsResponse>("/api/findings", {
        connection: params.connection,
        check_type: params.check_type ?? "",
        severity: params.severity ?? "",
        schema: params.schema ?? "",
        q: params.q ?? "",
        page: String(params.page ?? 1),
      }),
    placeholderData: (prev) => prev,
  });
}

export function useTables(params: {
  connection: string;
  search?: string;
  sort?: string;
  order?: string;
  page?: number;
}) {
  return useQuery({
    queryKey: ["tables", params],
    queryFn: () =>
      fetchApi<TablesResponse>("/api/tables", {
        connection: params.connection,
        search: params.search ?? "",
        sort: params.sort ?? "table",
        order: params.order ?? "asc",
        page: String(params.page ?? 1),
      }),
    placeholderData: (prev) => prev,
  });
}

export function useTableDetail(
  schema: string,
  table: string,
  connection: string,
) {
  return useQuery({
    queryKey: ["table", schema, table, connection],
    queryFn: () =>
      fetchApi<TableDetailResponse>(`/api/table/${schema}/${table}`, {
        connection,
      }),
  });
}

export function useUsage(connection: string) {
  return useQuery({
    queryKey: ["usage", connection],
    queryFn: () => fetchApi<UsageResponse>("/api/usage", { connection }),
  });
}

export function useDbt(connection: string) {
  return useQuery({
    queryKey: ["dbt", connection],
    queryFn: () => fetchApi<DbtResponse>("/api/dbt", { connection }),
  });
}

export function useRefresh() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postApi<{ success: boolean }>("/api/refresh"),
    onSuccess: () => {
      void queryClient.invalidateQueries();
    },
  });
}
