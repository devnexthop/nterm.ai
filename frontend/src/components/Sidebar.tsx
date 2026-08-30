import { useMemo, useState, type DragEvent, type ReactNode } from "react";
import type { Customer, MenuItem, SavedSession } from "../types";
import { worksetKey } from "../layout";
import ContextMenu from "./ContextMenu";

function kindMark(kind: string) {
  if (kind === "simulator") return "▣";
  if (kind === "local") return "⌘";
  if (kind === "telnet") return "T";
  if (kind === "serial") return "⌇";
  return "↣";
}

function normFolder(s: string) {
  return (s || "").replace(/^\/+|\/+$/g, "");
}

type FolderNode = {
  name: string;
  path: string;
  sessions: SavedSession[];
  children: FolderNode[];
};

function buildTree(sessions: SavedSession[], extraFolders: string[]): FolderNode {
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

const EMPTY_KEY = "nterm.emptyFolders";
const FOLDER_MIME = "application/x-nterm-folder";
const SESSION_MIME = "application/x-nterm-session";

function loadEmpty(): Record<string, string[]> {
  try { return JSON.parse(localStorage.getItem(EMPTY_KEY) || "{}"); } catch { return {}; }
}
function saveEmpty(v: Record<string, string[]>) {
  try { localStorage.setItem(EMPTY_KEY, JSON.stringify(v)); } catch { /* */ }
}

function isTreeDrag(e: DragEvent) {
  return e.dataTransfer.types.includes(FOLDER_MIME) || e.dataTransfer.types.includes(SESSION_MIME);
}

export default function Sidebar({
  customers,
  activeWorkset,
  onOpen,
  onSelectFolder,
  onOpenFolder,
  onNewCustomer,
  onNewSession,
  onEditSession,
  onDuplicate,
  onVault,
  onDelete,
  onRenameFolder,
  onMoveFolder,
  onMoveSession,
  onQuickConnect,
  onHide,
  onDockStart,
}: {
  customers: Customer[];
  activeWorkset: string | null;
  onOpen: (c: Customer, s: SavedSession) => void;
  onSelectFolder: (c: Customer, folder: string) => void;
  onOpenFolder: (c: Customer, folder: string, sessions: SavedSession[]) => void;
  onNewCustomer: () => void;
  onNewSession: (c: Customer, folder?: string) => void;
  onEditSession: (c: Customer, s: SavedSession) => void;
  onDuplicate: (s: SavedSession) => void;
  onVault: (s: SavedSession) => void;
  onDelete: (s: SavedSession) => void;
  onRenameFolder: (c: Customer, fromFolder: string, toFolder: string) => Promise<void>;
  onMoveFolder: (fromCustomerId: number, fromFolder: string, toCustomerId: number, toParent: string) => Promise<void>;
  onMoveSession: (s: SavedSession, toCustomerId: number, folder: string) => Promise<void>;
  onQuickConnect: () => void;
  onHide: () => void;
  onDockStart?: () => void;
}) {
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const [foldOpen, setFoldOpen] = useState<Record<string, boolean>>({});
  const [menu, setMenu] = useState<{ x: number; y: number; items: MenuItem[] } | null>(null);
  const [empty, setEmpty] = useState<Record<string, string[]>>(loadEmpty);
  const [dropOn, setDropOn] = useState<string | null>(null);

  const trees = useMemo(() => {
    const m = new Map<number, FolderNode>();
    for (const c of customers) {
      m.set(c.id, buildTree(c.sessions, empty[String(c.id)] || []));
    }
    return m;
  }, [customers, empty]);

  function addEmptyFolder(c: Customer, parent = "") {
    const name = window.prompt("Folder name", "Site");
    if (!name?.trim()) return;
    const path = parent ? `${normFolder(parent)}/${normFolder(name)}` : normFolder(name);
    const next = { ...empty, [String(c.id)]: [...(empty[String(c.id)] || []), path] };
    setEmpty(next);
    saveEmpty(next);
    onSelectFolder(c, path);
  }

  async function acceptDrop(e: DragEvent, toCustomerId: number, toParent: string) {
    e.preventDefault();
    setDropOn(null);
    const folderRaw = e.dataTransfer.getData(FOLDER_MIME);
    const sessRaw = e.dataTransfer.getData(SESSION_MIME);
    if (folderRaw) {
      const d = JSON.parse(folderRaw) as { customerId: number; folder: string };
      await onMoveFolder(d.customerId, d.folder, toCustomerId, toParent);
      return;
    }
    if (sessRaw) {
      const d = JSON.parse(sessRaw) as { customerId: number; sessionId: number };
      const c = customers.find((x) => x.id === d.customerId);
      const s = c?.sessions.find((x) => x.id === d.sessionId);
      if (s) await onMoveSession(s, toCustomerId, toParent);
    }
  }

  function dropHandlers(key: string, toCustomerId: number, toParent: string) {
    return {
      onDragOver: (e: DragEvent) => {
        if (!isTreeDrag(e)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setDropOn(key);
      },
      onDragLeave: (e: DragEvent) => {
        if (e.currentTarget.contains(e.relatedTarget as Node)) return;
        setDropOn((cur) => (cur === key ? null : cur));
      },
      onDrop: (e: DragEvent) => acceptDrop(e, toCustomerId, toParent),
    };
  }

  function sessionRow(c: Customer, s: SavedSession, indent: number) {
    return (
      <div
        className="session-row"
        key={s.id}
        style={{ paddingLeft: 10 + indent * 12 }}
        draggable
        onDragStart={(e) => {
          e.dataTransfer.setData(SESSION_MIME, JSON.stringify({ customerId: c.id, sessionId: s.id }));
          e.dataTransfer.effectAllowed = "copyMove";
          e.currentTarget.classList.add("dragging");
        }}
        onDragEnd={(e) => e.currentTarget.classList.remove("dragging")}
        title="Drag onto a folder or customer to move · onto the tab strip to open"
        onClick={() => onOpen(c, s)}
        onContextMenu={(e) => {
          e.preventDefault();
          setMenu({
            x: e.clientX,
            y: e.clientY,
            items: [
              { label: "Open", run: () => onOpen(c, s) },
              { label: "Edit session", run: () => onEditSession(c, s) },
              { label: "Duplicate", run: () => onDuplicate(s) },
              { label: "Save username/password to vault", run: () => onVault(s) },
              { label: "—" },
              { label: "Delete", danger: true, run: () => onDelete(s) },
            ],
          });
        }}
      >
        <span>{kindMark(s.kind)}</span>
        <span>{s.name}</span>
        <small>{s.kind}</small>
      </div>
    );
  }

  function renderNode(c: Customer, node: FolderNode, indent: number): ReactNode {
    return (
      <>
        {node.children.map((child) => {
          const fid = `${c.id}:${child.path}`;
          const shown = foldOpen[fid] !== false;
          const on = activeWorkset === worksetKey(c.id, child.path);
          return (
            <div key={fid}>
              <div
                className={`folder-row ${on ? "on" : ""} ${dropOn === fid ? "drop-on" : ""}`}
                style={{ paddingLeft: 10 + indent * 12 }}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData(FOLDER_MIME, JSON.stringify({ customerId: c.id, folder: child.path }));
                  e.dataTransfer.effectAllowed = "move";
                }}
                onClick={() => onSelectFolder(c, child.path)}
                {...dropHandlers(fid, c.id, child.path)}
                onContextMenu={(e) => {
                  e.preventDefault();
                  setMenu({
                    x: e.clientX,
                    y: e.clientY,
                    items: [
                      { label: "Show this folder’s tabs", run: () => onSelectFolder(c, child.path) },
                      { label: "Open all in folder", run: () => onOpenFolder(c, child.path, collectSessions(child)) },
                      { label: "New session in folder", run: () => onNewSession(c, child.path) },
                      { label: "New folder inside", run: () => addEmptyFolder(c, child.path) },
                      { label: "Rename folder", run: async () => {
                        const to = window.prompt("Rename folder", child.path);
                        if (!to || to === child.path) return;
                        await onRenameFolder(c, child.path, normFolder(to));
                      } },
                      { label: "Delete folder", danger: true, run: async () => {
                        const n = collectSessions(child).length;
                        if (n && !window.confirm(`Move ${n} session${n === 1 ? "" : "s"} out of ${child.name}?`)) return;
                        const parent = child.path.includes("/") ? child.path.slice(0, child.path.lastIndexOf("/")) : "";
                        if (n) await onRenameFolder(c, child.path, parent);
                        const cid = String(c.id);
                        const next = {
                          ...empty,
                          [cid]: (empty[cid] || []).filter((f) => f !== child.path && !f.startsWith(child.path + "/")),
                        };
                        setEmpty(next);
                        saveEmpty(next);
                      } },
                    ],
                  });
                }}
              >
                <button
                  className="fold-chev"
                  onClick={(e) => { e.stopPropagation(); setFoldOpen({ ...foldOpen, [fid]: !shown }); }}
                  aria-label={shown ? "Collapse" : "Expand"}
                >{shown ? "▾" : "▸"}</button>
                <strong>{child.name}</strong>
                <small>{collectSessions(child).length}</small>
              </div>
              {shown && (
                <>
                  {renderNode(c, child, indent + 1)}
                  {child.sessions.map((s) => sessionRow(c, s, indent + 1))}
                </>
              )}
            </div>
          );
        })}
      </>
    );
  }

  return (
    <aside className="sidebar explorer">
      <div
        className="frame-head"
        data-frame="sessions"
        draggable
        onDragStart={() => onDockStart?.()}
        title="Drag to dock this explorer on another edge"
      >
        <span>Explorer</span>
        <span className="row">
          <button type="button" className="ghost" onClick={onQuickConnect} onMouseDown={(e) => e.stopPropagation()}>Quick</button>
          <button type="button" className="ghost" onClick={onNewCustomer} onMouseDown={(e) => e.stopPropagation()}>+ New</button>
          <button
            type="button"
            className="ghost frame-hide"
            title="Hide explorer (⌘⇧S)"
            onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); }}
            onClick={(e) => { e.stopPropagation(); onHide(); }}
          >Hide</button>
        </span>
      </div>
      {customers.map((c) => {
        const shown = open[c.id] !== false;
        const tree = trees.get(c.id)!;
        const rootOn = activeWorkset === worksetKey(c.id, "");
        const dropKey = `cust:${c.id}`;
        return (
          <div className="customer" key={c.id}>
            <header
              className={`${rootOn ? "on" : ""} ${dropOn === dropKey ? "drop-on" : ""}`}
              onClick={() => { setOpen({ ...open, [c.id]: !shown }); onSelectFolder(c, ""); }}
              {...dropHandlers(dropKey, c.id, "")}
            >
              <span className="dot" style={{ background: c.color }} />
              <strong>{c.name}</strong>
              <small style={{ marginLeft: "auto", color: "var(--muted)" }}>{c.sessions.length}</small>
            </header>
            {shown && (
              <>
                {renderNode(c, tree, 1)}
                {tree.sessions.map((s) => sessionRow(c, s, 1))}
                <div className="session-row" style={{ paddingLeft: 22 }} onClick={() => addEmptyFolder(c)}>+ folder</div>
                <div className="session-row" style={{ paddingLeft: 22 }} onClick={() => onNewSession(c)}>+ session</div>
              </>
            )}
          </div>
        );
      })}
      {menu && <ContextMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => setMenu(null)} />}
    </aside>
  );
}

function collectSessions(node: FolderNode): SavedSession[] {
  return [...node.sessions, ...node.children.flatMap(collectSessions)];
}
