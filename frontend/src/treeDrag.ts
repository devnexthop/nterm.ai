/** Drag payload kept in-module.

Custom MIME types like application/x-nterm-session are often stripped from
dataTransfer.types on dragover (Safari / WebKit). The tab strip and explorer
must not depend on those types being listed — only on this handle, plus
text/plain as a fallback.
*/
export type TreeDrag =
  | { kind: "session"; customerId: number; sessionId: number }
  | { kind: "folder"; customerId: number; folder: string };

export const SESSION_MIME = "application/x-nterm-session";
export const FOLDER_MIME = "application/x-nterm-folder";

let current: TreeDrag | null = null;

export function setTreeDrag(payload: TreeDrag, dt: DataTransfer) {
  current = payload;
  const json = JSON.stringify(payload);
  const mime = payload.kind === "session" ? SESSION_MIME : FOLDER_MIME;
  try { dt.setData(mime, json); } catch { /* some browsers reject custom types */ }
  try { dt.setData("text/plain", json); } catch { /* */ }
  dt.effectAllowed = payload.kind === "session" ? "copyMove" : "move";
}

export function peekTreeDrag(): TreeDrag | null {
  return current;
}

export function isTreeDrag(): boolean {
  return current !== null;
}

export function readTreeDrag(dt?: DataTransfer | null): TreeDrag | null {
  if (current) return current;
  if (!dt) return null;
  const raw = dt.getData(SESSION_MIME) || dt.getData(FOLDER_MIME) || dt.getData("text/plain");
  if (!raw) return null;
  try {
    const p = JSON.parse(raw) as TreeDrag;
    if (p && (p.kind === "session" || p.kind === "folder")) return p;
  } catch { /* */ }
  return null;
}

export function clearTreeDrag() {
  current = null;
}
