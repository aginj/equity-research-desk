"use client";

import { signOut } from "next-auth/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { IconChevronDown, IconLogOut, IconShield, IconSliders, IconUser } from "@/components/icons";
import { useWorkspace } from "@/components/WorkspaceProvider";
import { Badge, Skeleton, cx } from "@/components/ui";

export function UserMenu({ compact = false }: { compact?: boolean }) {
  const { auth, user, isAdmin } = useWorkspace();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (auth === "loading") {
    return <Skeleton className={cx("h-9 rounded-xl", compact ? "w-9" : "w-28")} />;
  }

  if (auth === "anonymous" || !user) {
    const callback = pathname && pathname !== "/signin" ? `?callbackUrl=${encodeURIComponent(pathname)}` : "";
    return (
      <Link
        href={`/signin${callback}`}
        className="inline-flex h-9 items-center gap-2 rounded-xl border border-border-strong bg-surface px-3 text-xs font-medium text-fg transition hover:bg-surface-hover"
      >
        <IconUser size={15} />
        <span className={compact ? "hidden sm:inline" : ""}>Sign in</span>
      </Link>
    );
  }

  const label = user.name || user.email || "Account";
  const initial = label.trim().charAt(0).toUpperCase();

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex h-9 items-center gap-2 rounded-xl border border-border bg-surface pl-1 pr-2 text-xs text-fg transition hover:bg-surface-hover"
      >
        <Avatar src={user.image} initial={initial} />
        {!compact ? <span className="max-w-[120px] truncate font-medium">{label}</span> : null}
        <IconChevronDown size={14} className="text-muted" />
      </button>

      {open ? (
        <div
          role="menu"
          className="fade-up absolute right-0 z-50 mt-2 w-64 overflow-hidden rounded-2xl border border-border bg-bg-elevated shadow-md"
        >
          <div className="flex items-center gap-3 border-b border-border px-4 py-3">
            <Avatar src={user.image} initial={initial} size={36} />
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-fg">{label}</div>
              {user.email && user.name ? <div className="truncate text-[11px] text-muted">{user.email}</div> : null}
            </div>
            {isAdmin ? <Badge tone="accent" className="ml-auto">Admin</Badge> : null}
          </div>
          <div className="p-1.5">
            <MenuLink href="/workspace" icon={<IconSliders size={16} />} label="Workspace" hint="Venue, appetite, watchlist" />
            {isAdmin ? <MenuLink href="/admin" icon={<IconShield size={16} />} label="Admin" hint="Universe, defaults, runs" /> : null}
            <button
              role="menuitem"
              onClick={() => void signOut({ callbackUrl: "/" })}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm text-fg-2 transition hover:bg-surface-2 hover:text-fg"
            >
              <span className="text-muted"><IconLogOut size={16} /></span>
              Sign out
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function MenuLink({ href, icon, label, hint }: { href: string; icon: React.ReactNode; label: string; hint: string }) {
  return (
    <Link
      role="menuitem"
      href={href}
      className="flex items-center gap-3 rounded-xl px-3 py-2 text-sm text-fg-2 transition hover:bg-surface-2 hover:text-fg"
    >
      <span className="text-muted">{icon}</span>
      <span className="min-w-0">
        <span className="block font-medium leading-tight text-fg">{label}</span>
        <span className="block text-[11px] leading-tight text-muted">{hint}</span>
      </span>
    </Link>
  );
}

function Avatar({ src, initial, size = 28 }: { src?: string | null; initial: string; size?: number }) {
  if (src) {
    // Provider avatars come from arbitrary hosts; a plain <img> avoids next/image domain config.
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt="" width={size} height={size} className="rounded-lg object-cover" referrerPolicy="no-referrer" />;
  }
  return (
    <span
      style={{ width: size, height: size }}
      className="flex items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent-2 text-[12px] font-semibold text-accent-fg"
    >
      {initial}
    </span>
  );
}
