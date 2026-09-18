import { useEffect, useRef, useState, useCallback, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useTheme } from "../hooks/useTheme";

import { useFeaturePermissions } from "../hooks/useFeaturePermissions";
import { ADMIN_NAV, RETAIL_NAV, isNavActive } from "./navConfig";
import { ThemeToggle } from "../components/ThemeToggle";
import { InfrastructureStatus } from "../components/InfrastructureStatus";
import { navigateToPaperOrder } from "../utils/paperOrderNavigation";

type Props = {
  children: ReactNode;
  /** Optional top bar actions (search, BUY CTA, etc.) */
  topActions?: ReactNode;
  title?: string;
};

const SIDEBAR_STORAGE_KEY = "ui_sidebar_collapsed";

function readSidebarCollapsed(): boolean {
  try {
    const v = localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (v === "1") return true;
    if (v === "0") return false;
  } catch {
    /* ignore */
  }
  // Default: collapsed only on narrow desktop (≤1280); mobile uses drawer
  if (typeof window !== "undefined" && window.matchMedia("(max-width: 1280px) and (min-width: 769px)").matches) {
    return true;
  }
  return false;
}

export function AppShell({ children, topActions, title }: Props) {
  const { user, logout, role } = useAuth();
  const { theme, toggleTheme } = useTheme();

  const location = useLocation();
  const isAdmin = role === "admin";
  const navigate = useNavigate();
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() =>
    typeof window === "undefined" ? false : readSidebarCollapsed(),
  );
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  // Persist collapse preference — never fight the toggle with media-query forced state
  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_STORAGE_KEY, sidebarCollapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [sidebarCollapsed]);

  useEffect(() => {
    setMobileMenuOpen(false);
    setProfileOpen(false);
  }, [location.pathname]);

  function toggleSidebar() {
    setSidebarCollapsed((c) => !c);
  }

  const profileRef = useRef<HTMLDivElement>(null);
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 768px)").matches,
  );

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 768px)");
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // Click outside + ESC to close profile menu
  useEffect(() => {
    if (!profileOpen) return;
    const handler = (e: MouseEvent | TouchEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false);
      }
    };
    const keyHandler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setProfileOpen(false);
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    document.addEventListener("keydown", keyHandler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
      document.removeEventListener("keydown", keyHandler);
    };
  }, [profileOpen]);

  const { canAccess } = useFeaturePermissions();

  const initials = (user?.full_name || user?.email || "U").slice(0, 1).toUpperCase();
  // Sidebar rail uses retail nav; Admin settings (Admin, Central Command, System Logs, Diagnostics) live inside Profile
  const baseNavItems = RETAIL_NAV;
  const navItems = baseNavItems.filter((item) => {
    if (item.featureKey && !canAccess(item.featureKey)) return false;
    return true;
  });

  const isStrategyTester =
    location.pathname.startsWith("/strategy-tester") ||
    location.pathname.startsWith("/strategy-comparison") ||
    location.pathname.startsWith("/stock");

  return (
    <div
      className={[
        "app-shell-v2",
        sidebarCollapsed ? "app-shell-v2--collapsed" : "app-shell-v2--expanded",
        mobileMenuOpen ? "app-shell-v2--mobile-open" : "",
        isStrategyTester ? "app-shell-v2--strategy-tester" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-theme-active={theme}
      data-sidebar={sidebarCollapsed ? "collapsed" : "expanded"}
    >
      {/* Desktop / tablet sidebar */}
      <aside className="app-sidebar" aria-label="Main navigation" data-collapsed={sidebarCollapsed ? "true" : "false"}>
        <div className="app-sidebar__brand">
          <Link to="/markets" className="app-brand-link" aria-label="Go to Markets">
            <span className="app-brand-mark" aria-hidden>
              TS
            </span>
            <span className="app-brand-text">TradeDesk</span>
          </Link>
          <button
            type="button"
            className="app-sidebar__collapse ds-icon-btn"
            onClick={toggleSidebar}
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-pressed={sidebarCollapsed}
            title={sidebarCollapsed ? "Expand" : "Collapse"}
            data-testid="sidebar-collapse-toggle"
          >
            {sidebarCollapsed ? "»" : "«"}
          </button>
        </div>

        <nav className="app-sidebar__nav">
          {navItems.map((item) => {
            const active = isNavActive(location.pathname, item);
            return (
              <NavLink
                key={item.id}
                to={item.path}
                data-testid={item.testId}
                className={`app-sidebar__link ${active ? "is-active" : ""}`}
                title={item.label}
              >
                <span className="app-sidebar__icon">{item.icon}</span>
                <span className="app-sidebar__label-wrap">
                  <span className="app-sidebar__label">{item.label}</span>
                  {item.badge ? <span className="app-sidebar__badge">{item.badge}</span> : null}
                </span>
              </NavLink>
            );
          })}
        </nav>

        <div className="app-sidebar__footer">
          <div className="sidebar-universe-card">
            <div className="sidebar-universe-label">Universe</div>
            <div className="sidebar-universe-box">
              <span className="sidebar-universe-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
              </span>
              <div className="sidebar-universe-text">
                <div className="sidebar-universe-count">Nifty 500</div>
                <div className="sidebar-universe-name">All stocks</div>
              </div>
            </div>
          </div>
          <div className="sidebar-theme-card">
            <span className="sidebar-theme-title">Theme</span>
            <button
              type="button"
              className="sidebar-theme-toggle"
              onClick={toggleTheme}
              aria-label="Toggle theme"
              title="Toggle theme"
            >
              <span className={`sidebar-theme-icon ${theme === "light" ? "is-active" : ""}`}>☼</span>
              <span className={`sidebar-theme-icon ${theme === "dark" ? "is-active" : ""}`}>●</span>
            </button>
          </div>
          <div
            className="sidebar-user-card"
            onClick={() => navigate("/profile")}
            role="button"
            tabIndex={0}
            aria-label="User profile"
          >
            <div className="sidebar-user-avatar">{initials}</div>
            <div className="sidebar-user-info">
              <div className="sidebar-user-name">{user?.full_name || user?.email || "Account"}</div>
              <div className="sidebar-user-email">{user?.email || "Signed in"}</div>
            </div>
            <div className="sidebar-user-chevron">⌄</div>
          </div>
        </div>
      </aside>

      {/* Main column */}
      <div className="app-main-column">
        {!isStrategyTester ? (
        <header className="app-topbar">
          <div className="app-topbar__left">
            <button
              type="button"
              className="ds-icon-btn app-topbar__menu"
              aria-label="Open navigation"
              onClick={() => setMobileMenuOpen(true)}
            >
              ☰
            </button>
            {title ? <h1 className="app-topbar__title">{title}</h1> : null}
          </div>
          <div className="app-topbar__actions">
            {topActions}
            <InfrastructureStatus variant="header" />
            <button
              type="button"
              className="ds-btn ds-btn--buy ds-btn--sm"
              data-testid="global-buy-cta"
              onClick={() =>
                navigateToPaperOrder(navigate, {
                  side: "BUY",
                  returnTo: `${location.pathname}${location.search || ""}`,
                })
              }
            >
              BUY
            </button>
            <button
              type="button"
              className="ds-btn ds-btn--sell ds-btn--sm"
              data-testid="global-sell-cta"
              onClick={() =>
                navigateToPaperOrder(navigate, {
                  side: "SELL",
                  returnTo: `${location.pathname}${location.search || ""}`,
                })
              }
            >
              SELL
            </button>
            <button
              type="button"
              className="ds-btn ds-btn--secondary ds-btn--sm"
              data-testid="global-paper-cta"
              onClick={() => navigate("/paper")}
            >
              Paper trade
            </button>
            <div className="nav-profile-wrap" ref={profileRef}>
              <button
                type="button"
                data-testid="nav-profile-menu"
                className="nav-profile-btn app-topbar__profile"
                onClick={() => setProfileOpen((o) => !o)}
                aria-expanded={profileOpen}
                aria-haspopup="menu"
              >
                <span className="nav-avatar" aria-hidden>
                  {initials}
                </span>
                <span className="nav-profile-label app-topbar__name">
                  {user?.full_name?.split(" ")[0] || "Profile"}
                </span>
              </button>
              {profileOpen ? (
                <div className={`nav-profile-menu ${isMobile ? "nav-profile-menu--mobile" : ""}`} role="menu">
                  <button type="button" role="menuitem" onClick={() => { setProfileOpen(false); navigate("/profile"); }}>
                    Profile
                  </button>
                  <button type="button" role="menuitem" onClick={() => { setProfileOpen(false); navigate("/profile?section=preferences"); }}>
                    Preferences
                  </button>
                  <button type="button" role="menuitem" onClick={() => { setProfileOpen(false); navigate("/paper"); }}>
                    Paper Desk
                  </button>
                  {canAccess("advanced_scanner") ? (
                    <button
                      type="button"
                      role="menuitem"
                      data-testid="nav-scanner-profile"
                      onClick={() => {
                        setProfileOpen(false);
                        navigate("/scanner");
                      }}
                    >
                      Scanner Dashboard
                    </button>
                  ) : null}
                  {isAdmin ? (
                    <>
                      <div className="nav-profile-divider" data-testid="nav-profile-admin-divider" />
                      {canAccess("admin_panel") ? (
                        <button
                          type="button"
                          role="menuitem"
                          data-testid="nav-admin-panel-profile"
                          onClick={() => {
                            setProfileOpen(false);
                            navigate("/admin");
                          }}
                        >
                          Admin
                        </button>
                      ) : null}
                      {canAccess("central_command") ? (
                        <button
                          type="button"
                          role="menuitem"
                          data-testid="nav-central-command-profile"
                          onClick={() => {
                            setProfileOpen(false);
                            navigate("/admin/command");
                          }}
                        >
                          Central Command
                        </button>
                      ) : null}
                      {canAccess("system_logs") ? (
                        <button
                          type="button"
                          role="menuitem"
                          data-testid="nav-system-logs-profile"
                          onClick={() => {
                            setProfileOpen(false);
                            navigate("/admin/logs");
                          }}
                        >
                          System Logs
                        </button>
                      ) : null}
                      <button
                        type="button"
                        role="menuitem"
                        data-testid="nav-diagnostics-profile"
                        onClick={() => {
                          setProfileOpen(false);
                          navigate("/diagnostics");
                        }}
                      >
                        Diagnostics
                      </button>
                    </>
                  ) : null}
                  <button
                    type="button"
                    role="menuitem"
                    className="danger"
                    onClick={() => {
                      setProfileOpen(false);
                      logout();
                    }}
                  >
                    Sign out
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </header>
        ) : null}

        <div className="app-content">{children}</div>
      </div>

      {/* Mobile drawer overlay */}
      {mobileMenuOpen ? (
        <button
          type="button"
          className="app-mobile-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileMenuOpen(false)}
        />
      ) : null}

      {/* Floating scan button — mobile only */}
      {canAccess("advanced_scanner") ? (
        <button
          type="button"
          className="floating-scan-btn"
          aria-label="Open scanner"
          title="Open scanner"
          onClick={() => navigate("/scanner")}
        >
          ⚡
        </button>
      ) : null}

      {/* Mobile bottom navigation */}
      <nav className="app-bottom-nav" aria-label="Primary">
        {RETAIL_NAV.filter((item) => item.mobilePrimary && item.id !== "profile").filter((item) => {
          if (item.featureKey && !canAccess(item.featureKey)) return false;
          return true;
        }).map((item) => {
          const active = isNavActive(location.pathname, item);
          return (
            <NavLink
              key={item.id}
              to={item.path}
              data-testid={`${item.testId}-mobile`}
              className={`app-bottom-nav__item ${active ? "is-active" : ""}`}
            >
              <span className="app-bottom-nav__icon">{item.icon}</span>
              <span className="app-bottom-nav__label">{item.label}</span>
            </NavLink>
          );
        })}
        <NavLink
          to="/profile"
          data-testid="nav-profile-mobile"
          className={`app-bottom-nav__item ${location.pathname.startsWith("/profile") ? "is-active" : ""}`}
        >
          <span className="app-bottom-nav__icon" aria-hidden>
            <span className="nav-avatar nav-avatar--sm">{initials}</span>
          </span>
          <span className="app-bottom-nav__label">Profile</span>
        </NavLink>
      </nav>
    </div>
  );
}
