import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchApi, postApi, putApi } from "../api";
import type {
  ConnectionsResponse,
  ContractsResponse,
  OverviewResponse,
  FindingsResponse,
  IntegrityResponse,
  TablesResponse,
  TableDetailResponse,
  UsageResponse,
  DbtResponse,
  DbtNodeTimingsResponse,
  DbtPreviousSqlResponse,
  DispositionHistoryResponse,
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
  disposition?: string;
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
        disposition: params.disposition ?? "",
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

export function useDbtPreviousSql(uniqueId: string | null, dbtRunId: number | null) {
  return useQuery({
    queryKey: ["dbtPreviousSql", uniqueId, dbtRunId],
    queryFn: () =>
      fetchApi<DbtPreviousSqlResponse>(
        `/api/dbt/node/${encodeURIComponent(uniqueId!)}/previous-sql`,
        dbtRunId ? { dbt_run_id: String(dbtRunId) } : {},
      ),
    enabled: uniqueId !== null,
  });
}

export function useDbtNodeTimings(uniqueId: string | null) {
  return useQuery({
    queryKey: ["dbtNodeTimings", uniqueId],
    queryFn: () =>
      fetchApi<DbtNodeTimingsResponse>(
        `/api/dbt/node/${encodeURIComponent(uniqueId!)}/timings`,
      ),
    enabled: uniqueId !== null,
  });
}

export function useContracts(connection: string) {
  return useQuery({
    queryKey: ["contracts", connection],
    queryFn: () =>
      fetchApi<ContractsResponse>("/api/contracts", { connection }),
  });
}

export function useIntegrity(connection: string) {
  return useQuery({
    queryKey: ["integrity", connection],
    queryFn: () =>
      fetchApi<IntegrityResponse>("/api/integrity", { connection }),
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

export function useBulkDisposition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      findingIds,
      disposition,
      comment,
    }: {
      findingIds: number[];
      disposition: string;
      comment?: string;
    }) =>
      putApi<{ success: boolean; count: number }>(
        "/api/findings/bulk-disposition",
        { finding_ids: findingIds, disposition, comment: comment ?? "" },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["findings"] });
      void queryClient.invalidateQueries({ queryKey: ["table"] });
      void queryClient.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export function useSetDisposition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      findingId,
      disposition,
      comment,
    }: {
      findingId: number;
      disposition: string;
      comment?: string;
    }) =>
      putApi<{ success: boolean; disposition_id: number }>(
        `/api/findings/${findingId}/disposition`,
        { disposition, comment: comment ?? "" },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["findings"] });
      void queryClient.invalidateQueries({ queryKey: ["table"] });
      void queryClient.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export function useDispositionHistory(findingId: number | null) {
  return useQuery({
    queryKey: ["dispositionHistory", findingId],
    queryFn: () =>
      fetchApi<DispositionHistoryResponse>(
        `/api/findings/${findingId}/dispositions`,
      ),
    enabled: findingId !== null,
  });
}
