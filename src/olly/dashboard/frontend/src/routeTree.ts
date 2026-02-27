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
import { HistoryPage } from "./routes/history";
import { UsagePage } from "./routes/usage";
import { DbtPage } from "./routes/dbt";

type ConnectionSearch = { connection?: string };

const rootRoute = createRootRoute({
  component: RootLayout,
  validateSearch: (search: Record<string, unknown>): ConnectionSearch => ({
    connection: (search.connection as string) || undefined,
  }),
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: IndexPage,
});

const findingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/findings",
  component: FindingsPage,
});

const tablesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tables",
  component: TablesPage,
});

const tableDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/table/$schema/$table",
  component: TableDetailPage,
});

const historyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/history",
  component: HistoryPage,
});

const usageRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/usage",
  component: UsagePage,
});

const dbtRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/dbt",
  component: DbtPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  findingsRoute,
  tablesRoute,
  tableDetailRoute,
  historyRoute,
  usageRoute,
  dbtRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
