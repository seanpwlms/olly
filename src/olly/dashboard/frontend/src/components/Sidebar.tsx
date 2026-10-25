import { Link, useRouterState } from "@tanstack/react-router";
import { useConnections, useNav } from "../hooks/queries";
import { useConnection } from "../hooks/useConnection";
import { useTheme } from "../hooks/useTheme";
import { NavIcon } from "./NavIcon";
import { formatTimestamp, isCheckStale, timeAgo } from "../utils/time";
import type { NavSection } from "../types";

export const navLinks = [
  { to: "/", label: "Overview", icon: "overview", section: null },
  { to: "/findings", label: "Findings", icon: "findings", section: "findings" },
  { to: "/tables", label: "Tables", icon: "tables", section: null },
  { to: "/contracts", label: "Contracts", icon: "contracts", section: "contracts" },
  { to: "/integrity", label: "Integrity", icon: "integrity", section: "integrity" },
  { to: "/usage", label: "Usage", icon: "usage", section: null },
  { to: "/dbt", label: "dbt", icon: "dbt", section: "dbt" },
] as const;

const THEME_ICON_PATHS = {
  light: "M12 3v2M12 19v2M5.64 5.64l1.41 1.41M16.95 16.95l1.41 1.41M3 12h2M19 12h2M5.64 18.36l1.41-1.41M16.95 7.05l1.41-1.41M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  dark: "M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z",
  system: "M4 5h16v11H4zM9 20h6M12 16v4",
} as const;

function ThemeToggle({ collapsed }: { collapsed: boolean }) {
  const { theme, setTheme } = useTheme();
  const next = theme === "light" ? "dark" : theme === "dark" ? "system" : "light";
  return (
    <button
      onClick={() => setTheme(next)}
      aria-label={`Theme: ${theme}. Switch to ${next}`}
      className={`flex w-full items-center gap-2.5 rounded-lg py-2 text-sm text-gray-400 hover:bg-gray-800 hover:text-white transition-colors cursor-pointer ${
        collapsed ? "justify-center px-0" : "px-3"
      }`}
      title={`Theme: ${theme} (click for ${next})`}
    >
      <svg className="h-5 w-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={THEME_ICON_PATHS[theme]} />
      </svg>
      {!collapsed && <span className="capitalize">{theme}</span>}
    </button>
  );
}

/** Chevron button that collapses/expands the desktop sidebar. */
function CollapseToggle({ collapsed, onClick }: { collapsed: boolean; onClick: () => void }) {
  const label = collapsed ? "Expand sidebar" : "Collapse sidebar";
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className="rounded-lg p-1 text-gray-400 hover:bg-gray-800 hover:text-white transition-colors cursor-pointer"
    >
      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d={collapsed ? "M13 6l6 6-6 6M5 6l6 6-6 6" : "M11 6l-6 6 6 6M19 6l-6 6 6 6"} />
      </svg>
    </button>
  );
}

/** Collapsed-mode stand-in for NavBadges: a dot on the icon, red if any errors. */
function NavDot({ section }: { section: NavSection | undefined }) {
  if (!section?.configured) return null;
  if (section.errors === 0 && section.warnings === 0) return null;
  const color = section.errors > 0 ? "bg-red-500" : "bg-amber-400";
  return (
    <span
      className={`absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full ring-2 ring-gray-900 ${color}`}
    />
  );
}

/** Tooltip text for a collapsed nav item, since the label and badges are hidden. */
function navTitle(label: string, section: NavSection | undefined) {
  if (!section) return label;
  if (!section.configured) return `${label} (not configured)`;
  const parts = [];
  if (section.errors > 0) parts.push(`${section.errors} error${section.errors === 1 ? "" : "s"}`);
  if (section.warnings > 0) parts.push(`${section.warnings} warning${section.warnings === 1 ? "" : "s"}`);
  return parts.length ? `${label} · ${parts.join(", ")}` : label;
}

/** Right-aligned error/warning counts for one nav item. */
function NavBadges({ section }: { section: NavSection | undefined }) {
  if (!section) return null;
  if (!section.configured) {
    return (
      <span
        className="ml-auto text-xs text-gray-400"
        title="Not configured"
      >
        off
      </span>
    );
  }
  if (section.errors === 0 && section.warnings === 0) return null;
  return (
    <span className="ml-auto flex items-center gap-1">
      {section.errors > 0 && (
        <span
          className="rounded-full bg-red-500/15 px-1.5 py-0.5 text-xs font-semibold leading-none text-red-400"
          title={`${section.errors} error${section.errors === 1 ? "" : "s"}`}
        >
          {section.errors}
        </span>
      )}
      {section.warnings > 0 && (
        <span
          className="rounded-full bg-amber-500/15 px-1.5 py-0.5 text-xs font-semibold leading-none text-amber-400"
          title={`${section.warnings} warning${section.warnings === 1 ? "" : "s"}`}
        >
          {section.warnings}
        </span>
      )}
    </span>
  );
}

/** Last successful check run — the trust signal for every number in the app. */
function LastCheck({
  lastCheckTime,
  collapsed,
}: {
  lastCheckTime: string | null | undefined;
  collapsed: boolean;
}) {
  if (collapsed) {
    // Just a status dot; the full time lives in the tooltip.
    const stale = lastCheckTime ? isCheckStale(lastCheckTime) : true;
    const title = lastCheckTime
      ? `Last check: ${timeAgo(lastCheckTime)} (${formatTimestamp(lastCheckTime)})`
      : "No check has run yet";
    return (
      <div className="flex justify-center py-1.5" title={title}>
        <span className={`h-2 w-2 rounded-full ${stale ? "bg-amber-400" : "bg-emerald-500"}`} />
      </div>
    );
  }
  if (!lastCheckTime) {
    return (
      <div className="px-3 py-1.5 text-xs text-gray-400">
        No check has run yet
      </div>
    );
  }
  const stale = isCheckStale(lastCheckTime);
  return (
    <div
      className="px-3 py-1.5 text-xs leading-tight"
      title={`Last check: ${formatTimestamp(lastCheckTime)}`}
    >
      <span className="block text-xs font-medium text-gray-400">
        Last check
      </span>
      <span className={stale ? "text-amber-400" : "text-gray-300"}>
        {timeAgo(lastCheckTime)}
        {stale && " · stale"}
      </span>
    </div>
  );
}

export function Sidebar({
  onNavigate,
  collapsed = false,
  onToggleCollapse,
}: {
  onNavigate?: () => void;
  collapsed?: boolean;
  /** Omitted for the mobile drawer, which is never collapsed. */
  onToggleCollapse?: () => void;
}) {
  const { data } = useConnections();
  const { connection, setConnection } = useConnection();
  const { data: nav } = useNav(connection);
  const currentPath = useRouterState({ select: (s) => s.location.pathname });

  const connections = data?.connections ?? [];
  const currentConnection = connection || data?.current || "";
  const sections = nav?.sections;

  const isActive = (to: string) => {
    if (to === "/") return currentPath === "/";
    // The table detail route (/table/:schema/:table) belongs under Tables.
    if (to === "/tables") return currentPath.startsWith("/table");
    return currentPath.startsWith(to);
  };

  return (
    <div className="flex h-full flex-col bg-gray-900 border-r border-gray-800">
      <div className={`flex items-center py-4 ${collapsed ? "justify-center px-2" : "justify-between px-5"}`}>
        {!collapsed && (
          <Link
            to="/"
            onClick={onNavigate}
            className="text-white font-semibold text-xl no-underline tracking-tight"
          >
            olly
          </Link>
        )}
        {onToggleCollapse && <CollapseToggle collapsed={collapsed} onClick={onToggleCollapse} />}
      </div>

      <nav className={`flex-1 overflow-y-auto overflow-x-hidden py-2 ${collapsed ? "px-2" : "px-3"}`}>
        <ul className="list-none m-0 p-0 space-y-0.5">
          {navLinks.map((link) => {
            const active = isActive(link.to);
            const section = link.section ? sections?.[link.section] : undefined;
            const unconfigured = section?.configured === false;
            return (
              <li key={link.to}>
                <Link
                  to={link.to}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  aria-label={collapsed ? link.label : undefined}
                  title={collapsed ? navTitle(link.label, section) : undefined}
                  className={`flex items-center gap-2.5 rounded-lg py-2 text-sm no-underline transition-colors ${
                    collapsed ? "justify-center px-0" : "px-3"
                  } ${
                    active
                      ? "bg-gray-800 text-white font-medium"
                      : unconfigured
                        ? "text-gray-400 hover:bg-gray-800/60 hover:text-gray-200"
                        : "text-gray-300 hover:bg-gray-800/60 hover:text-white"
                  }`}
                >
                  <span className="relative shrink-0">
                    <NavIcon
                      name={link.icon}
                      className={`h-5 w-5 ${active ? "text-accent-400" : ""}`}
                    />
                    {collapsed && <NavDot section={section} />}
                  </span>
                  {!collapsed && (
                    <>
                      {link.label}
                      <NavBadges section={section} />
                    </>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className={`border-t border-gray-800 py-3 space-y-2 ${collapsed ? "px-2" : "px-3"}`}>
        {/* The connection picker needs room; expand the sidebar to switch. */}
        {!collapsed && connections.length > 1 && (
          <label className="block">
            <span className="block px-3 pb-1 text-xs font-medium text-gray-400">
              Connection
            </span>
            <select
              className="w-full px-3 py-1.5 border border-gray-700 rounded-lg bg-gray-800 text-gray-200 text-sm cursor-pointer hover:border-gray-600 focus:outline-none focus:ring-2 focus:ring-accent-500/40 transition-colors"
              value={currentConnection}
              onChange={(e) => setConnection(e.target.value)}
            >
              {connections.map((conn) => (
                <option key={conn} value={conn}>
                  {conn}
                </option>
              ))}
            </select>
          </label>
        )}
        <LastCheck lastCheckTime={nav?.last_check_time} collapsed={collapsed} />
        <ThemeToggle collapsed={collapsed} />
      </div>
    </div>
  );
}
