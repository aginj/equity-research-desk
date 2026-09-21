"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import {
  IconDesk,
  IconHistory,
  IconMenu,
  IconShield,
  IconSliders,
  IconWire,
  IconX,
} from "@/components/icons";
import { MarketSwitcher } from "@/components/MarketSwitcher";
import { ThemeToggle } from "@/components/ThemeToggle";
import { UserMenu } from "@/components/UserMenu";
import { useWorkspace } from "@/components/WorkspaceProvider";
import { Badge, cx } from "@/components/ui";

type NavItem = {
  href: string;
  label: string;
  hint: string;
  icon: (p: { size?: number }) => ReactNode;
  /** Only rendered when the viewer has this access level. */
  requires?: "user" | "admin";
};

const NAV: NavItem[] = [
  { href: "/", label: "Desk", hint: "Ranked book", icon: IconDesk },
  { href: "/research", label: "Research", hint: "News & filings tape", icon: IconWire },
  { href: "/workspace", label: "Workspace", hint: "Venue, appetite, watchlist", icon: IconSliders, requires: "user" },
  { href: "/runs", label: "Runs", hint: "Audit history", icon: IconHistory },
  { href: "/admin", label: "Admin", hint: "Universe & desk defaults", icon: IconShield, requires: "admin" },
];

const TITLES: Record<string, string> = {
  "/signin": "Sign in",
  "/privacy": "Privacy",
  "/terms": "Terms",
};

function isActive(pathname: string, href: string) {
  return pathname === href || (href !== "/" && pathname.startsWith(href));
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { market, auth, isAdmin } = useWorkspace();
  const [menuOpen, setMenuOpen] = useState(false);

  const items = NAV.filter((item) => {
    if (item.requires === "admin") return isAdmin;
    // Workspace stays visible to anonymous visitors as the entry point to sign in.
    return true;
  });

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <div className="relative min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
      {/* Sidebar (desktop) */}
      <aside className="sticky top-0 hidden h-screen flex-col border-r border-border bg-bg-elevated/70 backdrop-blur-xl lg:flex">
        <Brand />
        <Nav pathname={pathname} items={items} signedIn={auth === "authenticated"} />
        <SidebarFooter />
      </aside>

      {/* Mobile drawer */}
      {menuOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <button
            aria-label="Close menu"
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setMenuOpen(false)}
          />
          <aside className="fade-up absolute inset-y-0 left-0 flex w-[280px] flex-col border-r border-border bg-bg-elevated shadow-md">
            <div className="flex items-center justify-between pr-3">
              <Brand />
              <button
                onClick={() => setMenuOpen(false)}
                aria-label="Close"
                className="flex h-9 w-9 items-center justify-center rounded-xl text-muted hover:bg-surface-2"
              >
                <IconX size={18} />
              </button>
            </div>
            <Nav pathname={pathname} items={items} signedIn={auth === "authenticated"} />
            <div className="space-y-3 border-t border-border p-4">
              <MarketSwitcher />
              <UserMenu />
            </div>
          </aside>
        </div>
      ) : null}

      {/* Main column */}
      <div className="flex min-h-screen min-w-0 flex-col">
        <header className="sticky top-0 z-40 border-b border-border bg-bg/70 backdrop-blur-xl">
          <div className="flex h-16 items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <button
                onClick={() => setMenuOpen(true)}
                aria-label="Open menu"
                className="flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-surface text-fg-2 lg:hidden"
              >
                <IconMenu size={18} />
              </button>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-fg">
                  {TITLES[pathname] ?? NAV.find((n) => isActive(pathname, n.href))?.label ?? "Idea"}
                </div>
                <div className="truncate text-xs text-muted">
                  {market ? `${market.country} · ${market.exchange}` : "Equity research desk"}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 sm:gap-3">
              <div className="hidden md:block">
                <MarketSwitcher compact />
              </div>
              <Clock timezone={market?.timezone ?? "UTC"} />
              <ThemeToggle />
              <UserMenu compact />
            </div>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mx-auto w-full max-w-[1400px]">{children}</div>
        </main>

        <footer className="border-t border-border px-4 py-4 text-[11px] leading-relaxed text-muted-2 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-[1400px] items-start gap-2">
            <IconShield size={14} className="mt-0.5 shrink-0" />
            <p>
              Research and education only. Equity Research Desk does not provide personalized investment advice, does not
              execute trades, and is not a broker-dealer or registered investment adviser. Past performance is not
              indicative of future results.{" "}
              <Link href="/privacy" className="underline underline-offset-2 hover:text-fg-2">Privacy</Link> ·{" "}
              <Link href="/terms" className="underline underline-offset-2 hover:text-fg-2">Terms</Link>
            </p>
          </div>
        </footer>
      </div>
    </div>
  );
}

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-3 px-5 py-5">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-accent to-accent-2 text-accent-fg shadow-[var(--shadow-glow)]">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M4 16l5-6 4 4 7-9" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold leading-snug tracking-tight text-fg">Equity Research Desk</span>
        <span className="block text-[11px] text-muted">Ranked, sourced theses</span>
      </span>
    </Link>
  );
}

function Nav({ pathname, items, signedIn }: { pathname: string; items: NavItem[]; signedIn: boolean }) {
  return (
    <nav className="flex flex-1 flex-col gap-1 px-3 pt-2">
      {items.map((item) => {
        const active = isActive(pathname, item.href);
        const Icon = item.icon;
        const locked = item.requires === "user" && !signedIn;
        return (
          <Link
            key={item.href}
            href={locked ? `/signin?callbackUrl=${encodeURIComponent(item.href)}` : item.href}
            aria-current={active ? "page" : undefined}
            className={cx(
              "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors",
              active ? "bg-accent-soft text-fg" : "text-fg-2 hover:bg-surface-2 hover:text-fg",
            )}
          >
            {active ? <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-accent" /> : null}
            <span className={cx("shrink-0", active ? "text-accent" : "text-muted group-hover:text-fg-2")}>
              <Icon size={18} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block font-medium leading-tight">{item.label}</span>
              <span className="block text-[11px] leading-tight text-muted">{locked ? "Sign in to unlock" : item.hint}</span>
            </span>
            {item.requires === "admin" ? <Badge tone="accent" className="text-[10px]">Admin</Badge> : null}
          </Link>
        );
      })}
    </nav>
  );
}

function SidebarFooter() {
  return (
    <div className="border-t border-border p-4">
      <div className="rounded-xl bg-surface-2 p-3 text-[11px] leading-relaxed text-muted">
        Agents propose, policy disposes. Licensed feeds and SEC EDGAR only — no publisher scraping.
      </div>
    </div>
  );
}

function Clock({ timezone }: { timezone: string }) {
  const [clock, setClock] = useState("");
  useEffect(() => {
    const tick = () =>
      setClock(
        new Intl.DateTimeFormat("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
          timeZone: timezone,
          timeZoneName: "short",
        }).format(new Date()),
      );
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [timezone]);

  return (
    <div className="mono hidden h-9 items-center rounded-xl border border-border bg-surface px-3 text-xs text-fg-2 sm:flex tabular">
      {clock || "--:--:--"}
    </div>
  );
}
