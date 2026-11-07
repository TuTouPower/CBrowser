import {
  useEffect,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router";
import {
  Globe2,
  Languages,
  Layers,
  LogOut,
  Menu,
  MonitorPlay,
  PanelLeft,
  PanelLeftClose,
  Settings as SettingsIcon,
  SunMoon,
  X,
} from "lucide-react";
import { useApiClient } from "../shared/api/client_context";
import { useAuth } from "../features/auth/useAuth";
import { useI18n } from "../i18n";
import { useTheme, type ThemePreference } from "../theme";
import { Banner, Button, DropdownMenu, IconButton } from "../shared/ui";
import { useRuntimeSnapshot } from "./useRuntimeSnapshot";
import { useSessionFocus } from "../features/browser-session/session_focus";

const MIN_WIDTH = 200;
const MAX_WIDTH = 360;
const DEFAULT_WIDTH = 232;
const COLLAPSED_WIDTH = 72;
const WIDTH_KEY = "cbrowser.sidebar.width";
const COLLAPSED_KEY = "cbrowser.sidebar.collapsed";
const SESSION_TARGET_KEY = "cbrowser.session.target";

function clampWidth(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_WIDTH;
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(value)));
}

function readWidth(): number {
  try {
    const stored = localStorage.getItem(WIDTH_KEY);
    return stored === null ? DEFAULT_WIDTH : clampWidth(Number(stored));
  } catch {
    return DEFAULT_WIDTH;
  }
}

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function useNarrowLayout(): boolean {
  const [narrow, setNarrow] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    return window.matchMedia("(max-width: 1023px)").matches;
  });
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(max-width: 1023px)");
    const onChange = () => setNarrow(query.matches);
    setNarrow(query.matches);
    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    }
    query.addListener(onChange);
    return () => query.removeListener(onChange);
  }, []);
  return narrow;
}

export function AppLayout() {
  const { t, locale, setLocale } = useI18n();
  const { preference, setPreference } = useTheme();
  const { logout } = useAuth();
  const client = useApiClient();
  const navigate = useNavigate();
  const location = useLocation();
  const narrow = useNarrowLayout();
  const { focusMode } = useSessionFocus();
  const isSessionPage = /^\/session\/[^/]+$/.test(location.pathname);

  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [width, setWidth] = useState(readWidth);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { runningCount, coordinatorError } = useRuntimeSnapshot(client);

  useEffect(() => {
    try {
      localStorage.setItem(WIDTH_KEY, String(width));
    } catch {
      return;
    }
  }, [width]);
  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      return;
    }
  }, [collapsed]);

  useEffect(() => {
    const handleHostPointerDown = (event: MouseEvent | PointerEvent) => {
      const active = document.activeElement;
      if (active && active.tagName === "IFRAME" && event.target !== active) {
        (active as HTMLElement).blur();
        window.focus();
      }
    };
    window.addEventListener("pointerdown", handleHostPointerDown, true);
    window.addEventListener("mousedown", handleHostPointerDown, true);
    return () => {
      window.removeEventListener("pointerdown", handleHostPointerDown, true);
      window.removeEventListener("mousedown", handleHostPointerDown, true);
    };
  }, []);

  const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;
    const onMove = (move: PointerEvent) => {
      setWidth(clampWidth(startWidth + move.clientX - startX));
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  const handleLogout = async () => {
    try {
      await logout();
    } catch {
      // Auth state is cleared locally; the route guard performs the redirect.
    }
    navigate("/login");
  };

  let sessionTarget: string | null = null;
  try {
    sessionTarget = sessionStorage.getItem(SESSION_TARGET_KEY);
  } catch {
    sessionTarget = null;
  }
  const sessionPath = sessionTarget
    ? `/session/${encodeURIComponent(sessionTarget)}`
    : "/session";

  const navItems = [
    { to: "/", label: t("navEnvironments"), icon: Layers, key: "navEnvironments" },
    { to: "/proxies", label: t("navProxies"), icon: Globe2, key: "navProxies" },
    { to: sessionPath, label: t("navSessions"), icon: MonitorPlay, key: "navSessions" },
    { to: "/settings", label: t("navSettings"), icon: SettingsIcon, key: "navSettings" },
  ];

  const themeItems = [
    { label: t("themeSystem"), value: "system" as ThemePreference },
    { label: t("themeLight"), value: "light" as ThemePreference },
    { label: t("themeDark"), value: "dark" as ThemePreference },
  ];

  const sidebarContent: ReactNode = (
    <div className="flex h-full flex-col bg-sidebar text-on-surface">
      <div className="flex h-12 shrink-0 items-center justify-between gap-sm border-b border-outline px-md">
        <Link to="/" className="flex items-center gap-sm overflow-hidden">
          <img src="/menubar-icon.svg" alt="" className="h-5 w-5 shrink-0" />
          {!collapsed && (
            <span className="truncate font-ui text-title-sm tracking-wide">CBrowser</span>
          )}
        </Link>
        {narrow ? (
          <IconButton label={t("closeNavigation")} onClick={() => setDrawerOpen(false)}>
            <X aria-hidden="true" className="h-4 w-4" />
          </IconButton>
        ) : (
          <IconButton
            label={collapsed ? t("sidebarExpand") : t("sidebarCollapse")}
            onClick={() => setCollapsed(!collapsed)}
          >
            {collapsed ? (
              <PanelLeft aria-hidden="true" className="h-4 w-4" />
            ) : (
              <PanelLeftClose aria-hidden="true" className="h-4 w-4" />
            )}
          </IconButton>
        )}
      </div>

      <nav aria-label={t("openNavigation")} className="flex-1 overflow-y-auto p-sm">
        <ul className="flex flex-col gap-xs">
          {navItems.map((item) => {
            const active = item.key === "navEnvironments"
              ? location.pathname === "/" || location.pathname.startsWith("/profiles/")
              : location.pathname.startsWith(item.to);
            const Icon = item.icon;
            return (
              <li key={item.key}>
                <Link
                  to={item.to}
                  aria-current={active ? "page" : undefined}
                  title={collapsed ? item.label : undefined}
                  onClick={() => setDrawerOpen(false)}
                  className="flex h-9 items-center gap-md rounded-md px-sm font-ui text-label-md text-on-surface-muted hover:bg-surface-hover hover:text-on-surface aria-[current=page]:bg-accent-soft aria-[current=page]:text-on-surface"
                >
                  <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
                  {!collapsed && <span className="truncate">{item.label}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="shrink-0 border-t border-outline p-sm">
        <div
          data-testid="running-count"
          className="mb-sm flex items-center gap-sm rounded-md bg-surface-subtle px-sm py-sm font-ui text-label-sm text-on-surface"
        >
          <span className="h-2 w-2 shrink-0 rounded-full bg-accent" aria-hidden="true" />
          {!collapsed && <span className="truncate">{t("runningProfiles", { count: runningCount })}</span>}
        </div>
        <div className="flex items-center justify-between gap-xs">
          <DropdownMenu
            ariaLabel={t("switchTheme")}
            trigger={
              <IconButton label={t("switchTheme")}>
                <SunMoon aria-hidden="true" className="h-4 w-4" />
              </IconButton>
            }
            items={themeItems.map((item) => ({
              label: `${preference === item.value ? "• " : ""}${item.label}`,
              onSelect: () => setPreference(item.value),
            }))}
          />
          <Button
            size="sm"
            aria-label={t("switchLanguage")}
            onClick={() => setLocale(locale === "en" ? "zh" : "en")}
          >
            <Languages aria-hidden="true" className="h-3.5 w-3.5" />
            {!collapsed && <span className="uppercase">{locale}</span>}
          </Button>
          <IconButton label={t("logOut")} onClick={handleLogout}>
            <LogOut aria-hidden="true" className="h-4 w-4" />
          </IconButton>
        </div>
      </div>
    </div>
  );

  const sidebarWidth = collapsed ? COLLAPSED_WIDTH : width;

  return (
    <div className="flex h-screen overflow-hidden bg-background text-on-surface">
      {narrow ? (
        <>
          <div className={`flex h-12 shrink-0 items-center gap-sm border-b border-outline bg-sidebar px-md${focusMode ? " hidden" : ""}`}>
            <IconButton label={t("openNavigation")} onClick={() => setDrawerOpen(true)}>
              <Menu aria-hidden="true" className="h-4 w-4" />
            </IconButton>
            <span className="font-ui text-title-sm">CBrowser</span>
          </div>
          {drawerOpen && (
            <div className={`fixed inset-0 z-40 flex${focusMode ? " hidden" : ""}`} data-testid="sidebar-drawer">
              <div
                className="absolute inset-0 bg-overlay"
                onClick={() => setDrawerOpen(false)}
                aria-hidden="true"
              />
              <aside
                data-testid="sidebar"
                style={{ width: sidebarWidth }}
                className="relative h-full shrink-0 border-r border-outline"
              >
                {sidebarContent}
              </aside>
            </div>
          )}
        </>
      ) : (
        <div className={`relative flex shrink-0${focusMode ? " hidden" : ""}`} style={{ width: sidebarWidth }}>
          <aside
            data-testid="sidebar"
            className="h-full w-full border-r border-outline"
          >
            {sidebarContent}
          </aside>
          {!collapsed && (
            <div
              data-testid="sidebar-resize-handle"
              role="separator"
              aria-label={t("sidebarResize")}
              aria-orientation="vertical"
              tabIndex={0}
              onPointerDown={startResize}
              onKeyDown={(event) => {
                if (event.key === "ArrowLeft") setWidth(clampWidth(width - 8));
                if (event.key === "ArrowRight") setWidth(clampWidth(width + 8));
              }}
              className="absolute -right-1 top-0 z-10 h-full w-2 cursor-col-resize"
            />
          )}
        </div>
      )}

      <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <div
          className={
            isSessionPage
              ? "flex min-h-0 flex-1 flex-col"
              : "mx-auto flex min-h-0 w-full max-w-page flex-1 flex-col px-lg py-lg"
          }
        >
          {coordinatorError && (
            <div className="mb-md" data-testid="runtime-coordinator-error-slot">
              <Banner tone="warning" testId="runtime-coordinator-error">
                {t("runtimeCoordinatorError", { error: coordinatorError })}
              </Banner>
            </div>
          )}
          <div className="flex min-h-0 flex-1 flex-col">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
}
