import type { Customer, SavedSession } from "./types";

export const EMPTY_FOLDERS_KEY = "nterm.emptyFolders";

export type FolderNode = {
  name: string;
  path: string;
  sessions: SavedSession[];
  children: FolderNode[];
};

export function normFolder(s: string) {
  return (s || "").replace(/^\/+|\/+$/g, "");
}

export function loadEmptyFolders(): Record<string, string[]> {
  try { return JSON.parse(localStorage.getItem(EMPTY_FOLDERS_KEY) || "{}"); } catch { return {}; }
}

export function saveEmptyFolders(v: Record<string, string[]>) {
  try { localStorage.setItem(EMPTY_FOLDERS_KEY, JSON.stringify(v)); } catch { /* */ }
}

export function buildTree(sessions: SavedSession[], extraFolders: string[]): FolderNode {
  const root: FolderNode = { name: "", path: "", sessions: [], children: [] };
  const index = new Map<string, FolderNode>([["", root]]);

  function ensure(path: string): FolderNode {
    const n = normFolder(path);
    if (index.has(n)) return index.get(n)!;
    const parts = n.split("/").filter(Boolean);
    let parent = root;
    let acc = "";
    for (const part of parts) {
      acc = acc ? `${acc}/${part}` : part;
      if (!index.has(acc)) {
        const node: FolderNode = { name: part, path: acc, sessions: [], children: [] };
        parent.children.push(node);
        index.set(acc, node);
      }
      parent = index.get(acc)!;
    }
    return parent;
  }

  for (const f of extraFolders) ensure(f);
  for (const s of sessions) {
    const f = normFolder(s.folder || "");
    if (!f) root.sessions.push(s);
    else ensure(f).sessions.push(s);
  }
  return root;
}

export function collectSessions(node: FolderNode): SavedSession[] {
  return [...node.sessions, ...node.children.flatMap(collectSessions)];
}

export function folderPaths(node: FolderNode): string[] {
  const out: string[] = [];
  for (const child of node.children) {
    out.push(child.path, ...folderPaths(child));
  }
  return out;
}

export function sessionBlob(c: Customer, s: SavedSession) {
  return `${c.name} ${s.name} ${s.host} ${s.kind} ${s.folder}`.toLowerCase();
}

export function nodeMatches(c: Customer, node: FolderNode, q: string): boolean {
  if (!q) return true;
  if (node.name.toLowerCase().includes(q) || node.path.toLowerCase().includes(q)) return true;
  if (node.sessions.some((s) => sessionBlob(c, s).includes(q))) return true;
  return node.children.some((ch) => nodeMatches(c, ch, q));
}

export type MoveDest = { customerId: number; folder: string; label: string };

export function moveDestinations(customers: Customer[], extra: Record<string, string[]>): MoveDest[] {
  const dests: MoveDest[] = [];
  for (const c of customers) {
    dests.push({ customerId: c.id, folder: "", label: c.name });
    const tree = buildTree(c.sessions, extra[String(c.id)] || []);
    for (const path of folderPaths(tree)) {
      dests.push({ customerId: c.id, folder: path, label: `${c.name} / ${path.replaceAll("/", " / ")}` });
    }
  }
  return dests;
}
