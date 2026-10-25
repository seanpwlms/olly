import { useEffect, useState } from "react";
import { Outlet, useRouterState } from "@tanstack/react-router";
import { Sidebar } from "../components/Sidebar";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { useSidebarCollapsed } from "../hooks/useSidebarCollapsed";

const SIDEBAR_WIDTH = "w-60";

export function RootLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { collapsed, toggle } = useSidebarCollapsed();
  const currentPath = useRouterState({ select: (s) => s.location.pathname });

  // Close the mobile drawer whenever the route changes.
  useEffect(() => setMobileOpen(false), [currentPath]);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 antialiased">
      {/* Desktop sidebar */}
      <aside
        className={`hidden lg:block fixed inset-y-0 left-0 z-30 transition-[width] duration-200 ${
          collapsed ? "w-16" : SIDEBAR_WIDTH
        }`}
      >
        <Sidebar collapsed={collapsed} onToggleCollapse={toggle} />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="lg:hidden">
          <div
            className="fixed inset-0 z-40 bg-black/50"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <aside className={`fixed inset-y-0 left-0 z-50 ${SIDEBAR_WIDTH}`}>
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      {/* Mobile top bar */}
      <header className="lg:hidden sticky top-0 z-20 flex items-center gap-3 bg-gray-900 px-4 py-3 border-b border-gray-800">
        <button
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation"
          className="text-gray-300 hover:text-white transition-colors cursor-pointer"
        >
          <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <span className="text-white font-semibold text-lg tracking-tight">olly</span>
      </header>

      <div className={`transition-[padding] duration-200 ${collapsed ? "lg:pl-16" : "lg:pl-60"}`}>
        <main className="max-w-7xl mx-auto px-4 py-6 sm:px-6 sm:py-8">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
