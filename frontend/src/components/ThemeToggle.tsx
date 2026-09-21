"use client";

import { useEffect, useState } from "react";

import { IconMoon, IconSun } from "@/components/icons";

export const THEME_STORAGE_KEY = "desk-theme";
type Theme = "light" | "dark";

/**
 * Inline snippet for <head>: applies the stored/system theme before first paint so there is no
 * flash. Kept as a string so it can be injected with dangerouslySetInnerHTML in the layout.
 */
export const THEME_BOOT_SCRIPT = `(function(){try{var k="${THEME_STORAGE_KEY}";var s=localStorage.getItem(k);var m=window.matchMedia("(prefers-color-scheme: dark)").matches;var t=s==="light"||s==="dark"?s:(m?"dark":"light");document.documentElement.setAttribute("data-theme",t);}catch(e){}})();`;

function readTheme(): Theme {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  const [theme, setTheme] = useState<Theme>("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setTheme(readTheme());
    setMounted(true);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Private mode / storage disabled: theme still applies for this session.
    }
    setTheme(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={mounted ? `Switch to ${theme === "dark" ? "light" : "dark"} theme` : "Toggle theme"}
      title="Toggle theme"
      className={`flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-surface text-fg-2 transition hover:bg-surface-hover hover:text-fg ${className}`}
    >
      {mounted && theme === "light" ? <IconMoon size={16} /> : <IconSun size={16} />}
    </button>
  );
}
