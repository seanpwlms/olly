import { useState } from "react";

const STORAGE_KEY = "olly-sidebar-collapsed";

/** Desktop sidebar collapsed/expanded preference (persisted to localStorage). */
export function useSidebarCollapsed() {
  const [collapsed, setCollapsedState] = useState(
    () => localStorage.getItem(STORAGE_KEY) === "true",
  );

  const setCollapsed = (value: boolean) => {
    localStorage.setItem(STORAGE_KEY, String(value));
    setCollapsedState(value);
  };

  return { collapsed, toggle: () => setCollapsed(!collapsed) };
}
