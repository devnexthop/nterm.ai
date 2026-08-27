export type TermTheme = {
  background: string;
  foreground: string;
  cursor: string;
  selectionBackground: string;
  black: string;
  red: string;
  green: string;
  yellow: string;
  blue: string;
  magenta: string;
  cyan: string;
  white: string;
};

export type ChromeTheme = {
  id: string;
  label: string;
  bg: string;
  panel: string;
  panel2: string;
  border: string;
  text: string;
  muted: string;
  accent: string;
  accent2: string;
  onAccent?: string;
  term: TermTheme;
};

export const THEMES: ChromeTheme[] = [
  {
    /* ValeronLabs house palette — --pit-black / --navy / --cyan from
       valeronlabs.com. Terminal red is lifted off the brand's #e10600 racing
       red, which is too dark to read as body text on a near-black ground. */
    id: "valeron",
    label: "Valeron (brand)",
    bg: "#05080d",
    panel: "#0b1520",
    panel2: "#101a26",
    border: "#1c2a3a",
    text: "#eef3f8",
    muted: "#9aa8b5",
    accent: "#3ec6ff",
    accent2: "#7ad7ff",
    onAccent: "#04121c",
    term: {
      background: "#070c14",
      foreground: "#dde8f2",
      cursor: "#3ec6ff",
      selectionBackground: "#1d3f57",
      black: "#05080d",
      red: "#ff6b6b",
      green: "#4ade80",
      yellow: "#ffd166",
      blue: "#3ec6ff",
      magenta: "#c084fc",
      cyan: "#7ad7ff",
      white: "#eef3f8",
    },
  },
  {
    id: "nexthop_dark",
    label: "NextHop Dark (team)",
    bg: "#000000",
    panel: "#00072d",
    panel2: "#061433",
    border: "#1d2c58",
    text: "#ffffff",
    muted: "#a1a1aa",
    accent: "#0e6ba8",
    accent2: "#06b6d4",
    onAccent: "#ffffff",
    term: {
      background: "#00072d",
      foreground: "#e8f4fc",
      cursor: "#06b6d4",
      selectionBackground: "#0e6ba8",
      black: "#000000",
      red: "#f87171",
      green: "#4ade80",
      yellow: "#fde047",
      blue: "#38bdf8",
      magenta: "#c084fc",
      cyan: "#06b6d4",
      white: "#ffffff",
    },
  },
  {
    id: "nexthop_light",
    label: "NextHop Light (team)",
    bg: "#f3f7fb",
    panel: "#ffffff",
    panel2: "#e8eef6",
    border: "#c5d3e0",
    text: "#00072d",
    muted: "#5b6b7c",
    accent: "#0e6ba8",
    accent2: "#0891b2",
    onAccent: "#ffffff",
    term: {
      background: "#f8fafc",
      foreground: "#0a1628",
      cursor: "#0e6ba8",
      selectionBackground: "#bae6fd",
      black: "#0a1628",
      red: "#b91c1c",
      green: "#15803d",
      yellow: "#a16207",
      blue: "#0e6ba8",
      magenta: "#7c3aed",
      cyan: "#0e7490",
      white: "#334155",
    },
  },
  {
    id: "relay",
    label: "NTerm Amber",
    bg: "#07090d",
    panel: "#0e1218",
    panel2: "#141a22",
    border: "#222b38",
    text: "#e6edf3",
    muted: "#8b98a5",
    accent: "#ffb020",
    accent2: "#3d9cf0",
    term: {
      background: "#0a0e14",
      foreground: "#d6deea",
      cursor: "#ffb020",
      selectionBackground: "#2a3a4a",
      black: "#0a0e14",
      red: "#f07178",
      green: "#3dd68c",
      yellow: "#ffb020",
      blue: "#3d9cf0",
      magenta: "#c792ea",
      cyan: "#5fd4e0",
      white: "#e6edf3",
    },
  },
  {
    id: "warp",
    label: "Warp Midnight",
    bg: "#0b1020",
    panel: "#12182c",
    panel2: "#181f38",
    border: "#2a3354",
    text: "#e8ecff",
    muted: "#8b93b8",
    accent: "#7aa2ff",
    accent2: "#c084fc",
    term: {
      background: "#0d1226",
      foreground: "#e8ecff",
      cursor: "#7aa2ff",
      selectionBackground: "#2a3354",
      black: "#0d1226",
      red: "#ff6b8a",
      green: "#4ade80",
      yellow: "#fbbf24",
      blue: "#7aa2ff",
      magenta: "#c084fc",
      cyan: "#22d3ee",
      white: "#e8ecff",
    },
  },
  {
    id: "crt_amber",
    label: "CRT Amber",
    bg: "#100c04",
    panel: "#1a1408",
    panel2: "#241c0c",
    border: "#3d2e10",
    text: "#ffb000",
    muted: "#a87820",
    accent: "#ffcc33",
    accent2: "#ff7a18",
    term: {
      background: "#120e06",
      foreground: "#ffb000",
      cursor: "#ffcc33",
      selectionBackground: "#4a3208",
      black: "#120e06",
      red: "#ff6a00",
      green: "#c4a000",
      yellow: "#ffcc33",
      blue: "#c48420",
      magenta: "#d07020",
      cyan: "#e0a040",
      white: "#ffd27a",
    },
  },
  {
    id: "putty",
    label: "PuTTY Classic",
    bg: "#000000",
    panel: "#1a1a1a",
    panel2: "#262626",
    border: "#3a3a3a",
    text: "#c0c0c0",
    muted: "#808080",
    accent: "#00ffff",
    accent2: "#00ff00",
    term: {
      background: "#000000",
      foreground: "#c0c0c0",
      cursor: "#00ff00",
      selectionBackground: "#003300",
      black: "#000000",
      red: "#ff0000",
      green: "#00ff00",
      yellow: "#ffff00",
      blue: "#0000ff",
      magenta: "#ff00ff",
      cyan: "#00ffff",
      white: "#c0c0c0",
    },
  },
  {
    id: "nord",
    label: "Nord",
    bg: "#2e3440",
    panel: "#3b4252",
    panel2: "#434c5e",
    border: "#4c566a",
    text: "#eceff4",
    muted: "#d8dee9",
    accent: "#88c0d0",
    accent2: "#81a1c1",
    term: {
      background: "#2e3440",
      foreground: "#d8dee9",
      cursor: "#88c0d0",
      selectionBackground: "#434c5e",
      black: "#3b4252",
      red: "#bf616a",
      green: "#a3be8c",
      yellow: "#ebcb8b",
      blue: "#81a1c1",
      magenta: "#b48ead",
      cyan: "#88c0d0",
      white: "#eceff4",
    },
  },
  {
    id: "solarized",
    label: "Solarized Dark",
    bg: "#002b36",
    panel: "#073642",
    panel2: "#0a4452",
    border: "#586e75",
    text: "#eee8d5",
    muted: "#93a1a1",
    accent: "#268bd2",
    accent2: "#2aa198",
    term: {
      background: "#002b36",
      foreground: "#839496",
      cursor: "#268bd2",
      selectionBackground: "#073642",
      black: "#073642",
      red: "#dc322f",
      green: "#859900",
      yellow: "#b58900",
      blue: "#268bd2",
      magenta: "#d33682",
      cyan: "#2aa198",
      white: "#eee8d5",
    },
  },
  {
    id: "high_contrast",
    label: "High Contrast",
    bg: "#000000",
    panel: "#0a0a0a",
    panel2: "#141414",
    border: "#ffffff",
    text: "#ffffff",
    muted: "#c8c8c8",
    accent: "#ffff00",
    accent2: "#00ffff",
    term: {
      background: "#000000",
      foreground: "#ffffff",
      cursor: "#ffff00",
      selectionBackground: "#333333",
      black: "#000000",
      red: "#ff5555",
      green: "#55ff55",
      yellow: "#ffff55",
      blue: "#5555ff",
      magenta: "#ff55ff",
      cyan: "#55ffff",
      white: "#ffffff",
    },
  },
];

export function applyTheme(id: string) {
  const t = THEMES.find((x) => x.id === id) || THEMES[0];
  const root = document.documentElement;
  root.style.setProperty("--bg", t.bg);
  root.style.setProperty("--panel", t.panel);
  root.style.setProperty("--panel2", t.panel2);
  root.style.setProperty("--border", t.border);
  root.style.setProperty("--text", t.text);
  root.style.setProperty("--muted", t.muted);
  root.style.setProperty("--accent", t.accent);
  root.style.setProperty("--accent2", t.accent2);
  root.style.setProperty("--on-accent", t.onAccent || "#111111");
  root.classList.toggle("theme-light", t.id.includes("light"));
  root.classList.toggle("theme-nexthop", t.id.startsWith("nexthop"));
  return t;
}
