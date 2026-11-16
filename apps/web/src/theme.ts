export const THEME_PRESETS = [
  {
    id: "secmate-dark",
    label: "SecMate Dark",
    description: "Deep navy with a violet security accent.",
    swatches: ["#090D15", "#202A3D", "#A597FF"],
  },
  {
    id: "blue-cyber",
    label: "Blue Cyber",
    description: "High-contrast navy with a bright blue accent.",
    swatches: ["#06101D", "#172D49", "#70B7FF"],
  },
  {
    id: "white",
    label: "White",
    description: "A bright enterprise workspace with clear contrast.",
    swatches: ["#F4F6F9", "#FFFFFF", "#2563EB"],
  },
] as const;

export type ThemeId = (typeof THEME_PRESETS)[number]["id"];

export const THEME_STORAGE_KEY = "secmate.theme";

export function isThemeId(value: string | null): value is ThemeId {
  return THEME_PRESETS.some((theme) => theme.id === value);
}

export function readTheme(): ThemeId {
  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (isThemeId(storedTheme)) return storedTheme;

  // Preserve the intent of the previously persisted binary theme setting.
  if (storedTheme === "light") return "white";
  if (storedTheme === "dark") return "secmate-dark";

  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "secmate-dark" : "white";
}

export function saveTheme(theme: ThemeId) {
  window.localStorage.setItem(THEME_STORAGE_KEY, theme);
}

export function themeLabel(theme: ThemeId) {
  return THEME_PRESETS.find((preset) => preset.id === theme)?.label ?? "SecMate Dark";
}
