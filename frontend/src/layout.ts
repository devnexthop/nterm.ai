export type Edge = "left" | "right" | "top" | "bottom";
export type FrameId = "sessions" | "ai" | "editor" | "commandbar";

export type FrameDock = {
  edge: Edge;
  sizePx: number;
  open: boolean;
};

export type LayoutState = Record<FrameId, FrameDock>;

const KEY = "nterm.layout";

export const DEFAULT_LAYOUT: LayoutState = {
  sessions: { edge: "left", sizePx: 260, open: true },
  ai: { edge: "right", sizePx: 320, open: true },
  editor: { edge: "left", sizePx: 400, open: false },
  commandbar: { edge: "bottom", sizePx: 72, open: true },
};

export function loadLayout(): LayoutState {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT_LAYOUT, sessions: { ...DEFAULT_LAYOUT.sessions }, ai: { ...DEFAULT_LAYOUT.ai }, editor: { ...DEFAULT_LAYOUT.editor }, commandbar: { ...DEFAULT_LAYOUT.commandbar } };
    const parsed = JSON.parse(raw) as Partial<LayoutState>;
    const next = { ...DEFAULT_LAYOUT };
    (Object.keys(DEFAULT_LAYOUT) as FrameId[]).forEach((id) => {
      next[id] = { ...DEFAULT_LAYOUT[id], ...(parsed[id] || {}) };
    });
    return next;
  } catch {
    return { ...DEFAULT_LAYOUT };
  }
}

export function saveLayout(state: LayoutState) {
  try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* private mode */ }
}

export function worksetKey(customerId: number, folder: string) {
  return `${customerId}:${(folder || "").replace(/^\/+|\/+$/g, "")}`;
}

export function parseWorkset(key: string | null): { customerId: number; folder: string } | null {
  if (!key) return null;
  const i = key.indexOf(":");
  if (i < 0) return null;
  const customerId = Number(key.slice(0, i));
  if (!Number.isFinite(customerId)) return null;
  return { customerId, folder: key.slice(i + 1) };
}

const WORKSETS = "nterm.worksets";

export type Workset = { tabIds: string[]; active: string | null; layout: "single" | "split" | "quad" };

export function loadWorksets(): Record<string, Workset> {
  try { return JSON.parse(localStorage.getItem(WORKSETS) || "{}"); } catch { return {}; }
}

export function saveWorksets(w: Record<string, Workset>) {
  try { localStorage.setItem(WORKSETS, JSON.stringify(w)); } catch { /* private mode */ }
}
