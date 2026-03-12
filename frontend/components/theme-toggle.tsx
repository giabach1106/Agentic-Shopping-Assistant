"use client";

import { MoonStar, SunMedium } from "lucide-react";
import { useEffect, useState } from "react";

import { THEME_EVENT_NAME, themeStorageKey } from "@/lib/auth";

type ThemeMode = "light" | "dark";

function readTheme(): ThemeMode {
  if (typeof document !== "undefined") {
    const appliedTheme = document.documentElement.dataset.theme;
    if (appliedTheme === "light" || appliedTheme === "dark") {
      return appliedTheme;
    }
  }

  if (typeof window !== "undefined") {
    const stored = localStorage.getItem(themeStorageKey()) as ThemeMode | null;
    if (stored === "light" || stored === "dark") {
      return stored;
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  return "light";
}

function applyTheme(theme: ThemeMode) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(themeStorageKey(), theme);
  window.dispatchEvent(new Event(THEME_EVENT_NAME));
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<ThemeMode>(readTheme);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const syncTheme = () => {
      const stored = localStorage.getItem(themeStorageKey());
      if (stored) {
        setTheme(readTheme());
        return;
      }
      const nextTheme = mediaQuery.matches ? "dark" : "light";
      applyTheme(nextTheme);
      setTheme(nextTheme);
    };

    const syncFromEvent = () => {
      setTheme(readTheme());
    };

    mediaQuery.addEventListener("change", syncTheme);
    window.addEventListener("storage", syncFromEvent);
    window.addEventListener(THEME_EVENT_NAME, syncFromEvent);

    return () => {
      mediaQuery.removeEventListener("change", syncTheme);
      window.removeEventListener("storage", syncFromEvent);
      window.removeEventListener(THEME_EVENT_NAME, syncFromEvent);
    };
  }, []);

  return (
    <button
      type="button"
      onClick={() => {
        const nextTheme = theme === "light" ? "dark" : "light";
        setTheme(nextTheme);
        applyTheme(nextTheme);
      }}
      className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-[color:var(--border)] bg-[color:var(--surface)] text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
      aria-label="Toggle theme"
    >
      {theme === "light" ? <MoonStar className="h-4 w-4" /> : <SunMedium className="h-4 w-4" />}
    </button>
  );
}
