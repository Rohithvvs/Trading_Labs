import type { ReactNode } from "react";
import type { FeatureKey } from "../types/featurePermissions";

export type NavItem = {
  id: string;
  label: string;
  path: string;
  /** Match path prefix for active state */
  match?: string;
  icon: ReactNode;
  testId: string;
  featureKey?: FeatureKey | string;
  /** Include in the mobile bottom nav (Profile is added separately). */
  mobilePrimary?: boolean;
  badge?: string;
};

const icon = (d: string) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d={d} />
  </svg>
);

const flaskIcon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2" />
    <path d="M8.5 2h7" />
    <path d="M7 16h10" />
  </svg>
);

const compareIcon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <rect x="3" y="4" width="7" height="16" rx="1.5" />
    <rect x="14" y="4" width="7" height="16" rx="1.5" />
  </svg>
);

/** Retail primary navigation — Markets, Strategy Tester, Paper Desk, Performance, Profile.
 *  Scanner lives inside Profile → Scanner Dashboard. */
export const RETAIL_NAV: NavItem[] = [
  {
    id: "markets",
    label: "Markets",
    path: "/markets",
    match: "/markets",
    testId: "nav-markets",
    mobilePrimary: true,
    icon: icon("M3 3v18h18 M7 14l4-4 3 3 5-6"),
  },
  {
    id: "strategy-tester",
    label: "Strategy Tester",
    path: "/strategy-tester",
    match: "/strategy-tester",
    testId: "nav-strategy-tester",
    featureKey: "advanced_scanner",
    mobilePrimary: true,
    icon: flaskIcon,
  },
  {
    id: "strategy-comparison",
    label: "Strategy Comparison",
    path: "/strategy-comparison",
    match: "/strategy-comparison",
    testId: "nav-strategy-comparison",
    featureKey: "advanced_scanner",
    icon: compareIcon,
  },
  {
    id: "paper",
    label: "Paper Desk",
    path: "/paper",
    match: "/paper",
    testId: "nav-paper-trading",
    mobilePrimary: true,
    icon: icon("M4 19h16 M6 16V8l6-4 6 4v8 M10 12h4"),
  },
  {
    id: "performance",
    label: "Performance",
    path: "/performance",
    match: "/performance",
    testId: "nav-performance",
    featureKey: "portfolio_analytics",
    icon: icon("M4 19V5 M8 19v-8 M12 19v-5 M16 19V9 M20 19v-3"),
  },
  {
    id: "profile",
    label: "Profile",
    path: "/profile",
    match: "/profile",
    testId: "nav-profile",
    icon: icon("M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4z M4 20a8 8 0 0 1 16 0"),
  },
];

/** Admin / ops — only when user.role === "admin" (Sprint 4) + feature access (Sprint 5) */
export const ADMIN_NAV: NavItem[] = [
  {
    id: "admin-panel",
    label: "Admin",
    path: "/admin",
    match: "/admin",
    testId: "nav-admin-panel",
    featureKey: "admin_panel",
    icon: icon("M12 1l3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 8h7z"),
  },
  {
    id: "admin-command",
    label: "Central Command",
    path: "/admin/command",
    match: "/admin/command",
    testId: "nav-central-command",
    featureKey: "central_command",
    icon: icon("M12 2l3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 9h7z"),
  },
  {
    id: "admin-logs",
    label: "System Logs",
    path: "/admin/logs",
    match: "/admin/logs",
    testId: "nav-system-logs",
    featureKey: "system_logs",
    icon: icon("M4 6h16 M4 12h16 M4 18h10"),
  },
  {
    id: "admin-diagnostics",
    label: "Diagnostics",
    path: "/diagnostics",
    match: "/diagnostics",
    testId: "nav-diagnostics",
    icon: icon("M12 2v4 M12 18v4 M4.93 4.93l2.83 2.83 M16.24 16.24l2.83 2.83 M2 12h4 M18 12h4 M4.93 19.07l2.83-2.83 M16.24 7.76l2.83-2.83"),
  },
];

export function isNavActive(pathname: string, item: NavItem): boolean {
  const m = item.match ?? item.path;
  if (m === "/") return pathname === "/";
  // Exact match for /admin so /admin/logs does not highlight Admin panel
  if (item.id === "admin-panel") {
    return pathname === "/admin" || pathname.startsWith("/admin?");
  }
  return pathname === m || pathname.startsWith(`${m}/`);
}
