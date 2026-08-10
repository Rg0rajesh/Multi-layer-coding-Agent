// frontend/src/hooks/useTheme.ts
import { useCallback, useEffect, useState } from "react";

export type ThemeMode = "light" | "dark" | "system";

const STORAGE_KEY = "agentx-theme";

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function resolveMode(mode: ThemeMode): "light" | "dark" {
  return mode === "system" ? (systemPrefersDark() ? "dark" : "light") : mode;
}

function applyTheme(resolved: "light" | "dark") {
  // The whole app keys off this one attribute — theme.css defines a
  // complete [data-theme="dark"] token set, not a filter over light mode,
  // per the spec's "not an inversion trick" line.
  document.documentElement.setAttribute("data-theme", resolved);
}

/**
 * Shared by the Navbar toggle and the Settings > General theme swatches —
 * both just call setMode, so switching from either place stays in sync
 * without any cross-component wiring.
 */
export function useTheme() {
  const [mode, setModeState] = useState<ThemeMode>(() => {
    return (localStorage.getItem(STORAGE_KEY) as ThemeMode | null) ?? "system";
  });

  useEffect(() => {
    applyTheme(resolveMode(mode));

    if (mode !== "system") return;

    // Only listen while "system" is actually selected — no point reacting
    // to OS-level changes if the person explicitly picked light or dark.
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme(resolveMode("system"));
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [mode]);

  const setMode = useCallback((next: ThemeMode) => {
    localStorage.setItem(STORAGE_KEY, next);
    setModeState(next);
  }, []);

  const toggle = useCallback(() => {
    setMode(resolveMode(mode) === "dark" ? "light" : "dark");
  }, [mode, setMode]);

  return { mode, resolved: resolveMode(mode), setMode, toggle };
}
