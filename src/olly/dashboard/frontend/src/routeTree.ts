import {
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import { RootLayout } from "./routes/__root";
import { IndexPage } from "./routes/index";
import { FindingsPage } from "./routes/findings";
import { TablesPage } from "./routes/tables";
import { TableDetailPage } from "./routes/table.$schema.$table";
import { UsagePage } from "./routes/usage";
import { DbtPage } from "./routes/dbt";

function parseConnection(search: Record<string, unknown>) {
  return { connection: (search.connection as string) || undefined };
}

export type FindingsSearch = {
  connection?: string;
  severity?: string;
  check_type?: string;
  schema?: string;
  q?: string;
  page?: number;
};

export type TablesSearch = {
  connection?: string;
  search?: string;
  sort?: string;
  order?: string;
  page?: number;
};

export type DbtSearch = {
  connection?: string;
  resource_type?: string;
  severity?: string;
};

const rootRoute = createRootRoute({
  component: RootLayout,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: IndexPage,
});

export const findingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/findings",
  component: FindingsPage,
  validateSearch: (search: Record<string, unknown>): FindingsSearch => ({
    ...parseConnection(search),
    severity: (search.severity as string) || undefined,
    check_type: (search.check_type as string) || undefined,
    schema: (search.schema as string) || undefined,
    q: (search.q as string) || undefined,
    page: Number(search.page) || undefined,
  }),
});

export const tablesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tables",
  component: TablesPage,
  validateSearch: (search: Record<string, unknown>): TablesSearch => ({
    ...parseConnection(search),
    search: (search.search as string) || undefined,
    sort: (search.sort as string) || undefined,
    order: (search.order as string) || undefined,
    page: Number(search.page) || undefined,
  }),
});

const tableDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/table/$schema/$table",
  component: TableDetailPage,
});

const usageRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/usage",
  component: UsagePage,
});

export const dbtRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/dbt",
  component: DbtPage,
  validateSearch: (search: Record<string, unknown>): DbtSearch => ({
    ...parseConnection(search),
    resource_type: (search.resource_type as string) || undefined,
    severity: (search.severity as string) || undefined,
  }),
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  findingsRoute,
  tablesRoute,
  tableDetailRoute,
  usageRoute,
  dbtRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
