"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { IconBell } from "@/components/icons";
import { useWorkspace } from "@/components/WorkspaceProvider";
import { Badge, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { ideaHref } from "@/lib/format";
import type { DeskNotification } from "@/lib/types";

export function NotificationBell() {
  const { auth } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [rows, setRows] = useState<DeskNotification[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (auth !== "authenticated") return;
    let cancelled = false;
    const load = () => {
      api
        .notifications()
        .then((payload) => {
          if (cancelled) return;
          setUnread(payload.unread);
          setRows(payload.notifications);
        })
        .catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [auth]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  if (auth !== "authenticated") return null;

  async function markAll() {
    await api.markNotificationsRead();
    setUnread(0);
    setRows((current) => current.map((row) => ({ ...row, read_at: row.read_at ?? new Date().toISOString() })));
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={unread ? `${unread} unread notifications` : "Notifications"}
        onClick={() => setOpen((v) => !v)}
        className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-surface text-fg-2 transition hover:bg-surface-hover hover:text-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
      >
        <IconBell size={16} />
        {unread > 0 ? (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold text-accent-fg">
            {unread > 9 ? "9+" : unread}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="absolute right-0 z-50 mt-2 w-80 overflow-hidden rounded-xl border border-border bg-bg-elevated shadow-md">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-xs font-semibold text-fg">Notifications</span>
            {unread > 0 ? (
              <button type="button" onClick={() => void markAll()} className="text-[11px] text-accent hover:underline">
                Mark all read
              </button>
            ) : (
              <Badge tone="neutral">{rows.length}</Badge>
            )}
          </div>
          <ul className="max-h-80 overflow-y-auto">
            {rows.length === 0 ? (
              <li className="px-3 py-4 text-xs text-muted">Nothing yet. Watchlist moves and scheduled books land here.</li>
            ) : (
              rows.map((row) => (
                <li key={row.id} className={cx("border-b border-border px-3 py-2.5 last:border-0", !row.read_at && "bg-accent-soft/40")}>
                  <div className="text-xs font-medium text-fg">{row.title}</div>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-muted">{row.body}</p>
                  <div className="mt-1 flex items-center justify-between text-[10px] text-muted-2">
                    <span>{relativeTime(row.created_at)}</span>
                    {row.ticker ? (
                      <Link href={ideaHref(row.ticker)} className="text-accent hover:underline" onClick={() => setOpen(false)}>
                        {row.ticker}
                      </Link>
                    ) : null}
                  </div>
                </li>
              ))
            )}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
