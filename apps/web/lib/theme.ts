export type ThemeId = "default" | "warm" | "focus" | "high-contrast" | "dark";

export const THEME_PRESETS: { id: ThemeId; label: string }[] = [
  { id: "default", label: "Default" },
  { id: "warm", label: "Warm" },
  { id: "focus", label: "Focus" },
  { id: "high-contrast", label: "High contrast" },
  { id: "dark", label: "Dark (VS Code)" },
];

const STORAGE_KEY = "app_theme";

export function getStoredTheme(): ThemeId {
  if (typeof window === "undefined") return "default";
  const v = localStorage.getItem(STORAGE_KEY) as ThemeId | null;
  if (v && THEME_PRESETS.some((p) => p.id === v)) return v;
  return "default";
}

export function applyTheme(theme: ThemeId): void {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(STORAGE_KEY, theme);
}
