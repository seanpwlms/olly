import { Outlet, Link, useRouterState } from "@tanstack/react-router";
import { useConnections } from "../hooks/queries";
import { useConnection } from "../hooks/useConnection";
import { useTheme } from "../hooks/useTheme";

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const next = theme === "light" ? "dark" : theme === "dark" ? "system" : "light";
  const icon = theme === "light" ? "\u2600" : theme === "dark" ? "\u263E" : "\u25D0";
  return (
    <button
      onClick={() => setTheme(next)}
      className="text-gray-400 hover:text-white transition-colors text-sm"
      title={`Theme: ${theme}`}
    >
      {icon}
    </button>
  );
}

export function RootLayout() {
  const { data } = useConnections();
  const { connection, setConnection } = useConnection();
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;

  const connections = data?.connections ?? [];
  const currentConnection = connection || data?.current || "";

  const navLinks = [
    { to: "/findings", label: "Findings" },
    { to: "/tables", label: "Tables" },
  ] as const;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 antialiased">
      <header className="bg-gray-900 shadow-lg">
        <nav className="max-w-6xl mx-auto flex items-center gap-6 px-6 py-3">
          <Link to="/" className="text-white font-bold text-xl no-underline tracking-tight">
            olly
          </Link>
          {navLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className={`text-sm no-underline pb-0.5 transition-colors ${
                currentPath === link.to
                  ? "text-white border-b-2 border-blue-400"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {link.label}
            </Link>
          ))}
          <Link
            to="/usage"
            className={`ml-auto text-xs no-underline transition-colors ${
              currentPath === "/usage"
                ? "text-white"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            Usage
          </Link>
          <ThemeToggle />
          {connections.length > 1 && (
            <select
              className="px-3 py-1.5 border border-gray-600 rounded-lg bg-white text-gray-800 text-sm cursor-pointer hover:border-gray-300 transition-colors"
              value={currentConnection}
              onChange={(e) => setConnection(e.target.value)}
            >
              {connections.map((conn) => (
                <option key={conn} value={conn}>
                  {conn}
                </option>
              ))}
            </select>
          )}
        </nav>
      </header>
      <main className="max-w-6xl mx-auto px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
