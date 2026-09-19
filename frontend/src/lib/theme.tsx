/**
 * Theme preference: light, dark, or follow the device.
 *
 * The stylesheet already handles all three states — tokens are defined on bare
 * `:root` for light, redefined under `prefers-color-scheme: dark` guarded by
 * `:root:not([data-theme="light"])`, and again under `:root[data-theme="dark"]`.
 * So this only has to stamp the attribute; setting it to "system" removes it
 * and the media query takes over again.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ThemeChoice = "light" | "dark" | "system";

const STORAGE_KEY = "parkspace.theme";

interface ThemeState {
  choice: ThemeChoice;
  /** What is actually on screen right now. */
  resolved: "light" | "dark";
  setChoice: (choice: ThemeChoice) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeState | null>(null);

function readStored(): ThemeChoice {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === "light" || value === "dark" || value === "system") return value;
  } catch {
    /* private mode or blocked storage — fall through to the device setting */
  }
  return "system";
}

function systemIsDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

function apply(choice: ThemeChoice) {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>(readStored);
  const [systemDark, setSystemDark] = useState(systemIsDark);

  useEffect(() => apply(choice), [choice]);

  // Keep `resolved` honest when the device flips while "system" is selected.
  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return;
    const listener = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, []);

  const setChoice = useCallback((next: ThemeChoice) => {
    setChoiceState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* the choice still applies for this session */
    }
  }, []);

  const resolved: "light" | "dark" = choice === "system" ? (systemDark ? "dark" : "light") : choice;

  // The toggle flips what is on screen, which is what someone expects a single
  // button to do — it does not cycle through "system".
  const toggle = useCallback(
    () => setChoice(resolved === "dark" ? "light" : "dark"),
    [resolved, setChoice],
  );

  const value = useMemo<ThemeState>(
    () => ({ choice, resolved, setChoice, toggle }),
    [choice, resolved, setChoice, toggle],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}

/** Applied before React mounts so the first paint is already the right theme. */
export function applyStoredThemeEarly() {
  apply(readStored());
}
