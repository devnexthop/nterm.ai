import { useMemo, useState, type DragEvent, type KeyboardEvent, type ReactNode } from "react";
import type { Customer, MenuItem, SavedSession } from "../types";
import { worksetKey } from "../layout";
import {
  buildTree,
  collectSessions,
  loadEmptyFolders,
  nodeMatches,
  normFolder,
  saveEmptyFolders,
  sessionBlob,
  type FolderNode,
} from "../sessionTree";
import {
  clearTreeDrag,
  isTreeDrag,
  peekTreeDrag,
  readTreeDrag,
  setTreeDrag,
} from "../treeDrag";
import ContextMenu from "./ContextMenu";

function kindMark(kind: string) {
  if (kind === "simulator") return "▣";
  if (kind === "local") return "⌘";
  if (kind === "telnet") return "T";
  if (kind === "serial") return "⌇";
  return "↣";
}

type Sel =
  | { k: "c"; id: number }
  | { k: "f"; id: number; path: string }
  | { k: "s"; id: number; sid: number };

type Rename = Sel;

function destIsSelfFolder(fromPath: string, toParent: string) {
  return toParent === fromPath || toParent.startsWith(fromPath + "/");
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
  onRenameCustomer,
  onDeleteCustomer,
  onRenameSession,
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
  onRenameCustomer: (c: Customer, name: string) => Promise<void>;
  onDeleteCustomer: (c: Customer) => Promise<void>;
  onRenameSession: (s: SavedSession, name: string) => Promise<void>;
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
  const [empty, setEmpty] = useState(loadEmptyFolders);
  const [dropOn, setDropOn] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [sel, setSel] = useState<Sel | null>(null);
  const [rename, setRename] = useState<Rename | null>(null);

  const trees = useMemo(() => {
    const m = new Map<number, FolderNode>();
    for (const c of customers) {
      m.set(c.id, buildTree(c.sessions, empty[String(c.id)] || []));
    }
    return m;
  }, [customers, empty]);

  const q = filter.trim().toLowerCase();

  function onExplorerKey(e: KeyboardEvent) {
    if (e.target instanceof HTMLInputElement) return;
    if (e.key === "F2" && sel && !rename) {
      e.preventDefault();
      setRename(sel);
    }
    if (e.key === "Enter" && sel?.k === "s" && !rename) {
      const c = customers.find((x) => x.id === sel.id);
      const s = c?.sessions.find((x) => x.id === sel.sid);
      if (c && s) {
        e.preventDefault();
        onOpen(c, s);
      }
    }
  }

  function addEmptyFolder(c: Customer, parent = "") {
    const name = window.prompt("Folder name", "Site");
    if (!name?.trim()) return;
    const path = parent ? `${normFolder(parent)}/${normFolder(name)}` : normFolder(name);
    const next = { ...empty, [String(c.id)]: [...(empty[String(c.id)] || []), path] };
    setEmpty(next);
    saveEmptyFolders(next);
    onSelectFolder(c, path);
    setSel({ k: "f", id: c.id, path });
  }

  function selectedTarget(): { c: Customer; folder: string } | null {
    if (!sel) return customers[0] ? { c: customers[0], folder: "" } : null;
    const c = customers.find((x) => x.id === sel.id);
    if (!c) return null;
    if (sel.k === "f") return { c, folder: sel.path };
    if (sel.k === "s") {
      const s = c.sessions.find((x) => x.id === sel.sid);
      return { c, folder: s?.folder || "" };
    }
    return { c, folder: "" };
  }

  async function acceptDrop(e: DragEvent, toCustomerId: number, toParent: string) {
    e.preventDefault();
    setDropOn(null);
    const payload = readTreeDrag(e.dataTransfer);
    clearTreeDrag();
    if (!payload) return;
    if (payload.kind === "folder") {
      if (payload.customerId === toCustomerId && destIsSelfFolder(payload.folder, toParent)) return;
      await onMoveFolder(payload.customerId, payload.folder, toCustomerId, toParent);
      return;
    }
    const c = customers.find((x) => x.id === payload.customerId);
    const s = c?.sessions.find((x) => x.id === payload.sessionId);
    if (s) await onMoveSession(s, toCustomerId, toParent);
  }

  function dropHandlers(key: string, toCustomerId: number, toParent: string) {
    return {
      onDragOver: (e: DragEvent) => {
        if (!isTreeDrag()) return;
        const p = peekTreeDrag();
        if (p?.kind === "folder" && p.customerId === toCustomerId && destIsSelfFolder(p.folder, toParent)) return;
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

  function isRenaming(r: Rename) {
    if (!rename) return false;
    if (rename.k !== r.k || rename.id !== r.id) return false;
    if (r.k === "f" && rename.k === "f") return rename.path === r.path;
    if (r.k === "s" && rename.k === "s") return rename.sid === r.sid;
    return true;
  }

  function label(value: string, r: Rename, onCommit: (name: string) => void) {
    if (!isRenaming(r)) {
      return (
        <span
          className="ex-label"
          onDoubleClick={(e) => {
            e.stopPropagation();
            e.preventDefault();
            setRename(r);
          }}
        >{value}</span>
      );
    }
    return (
      <input
        className="ex-rename"
        defaultValue={value}
        autoFocus
        onClick={(e) => e.stopPropagation()}
        onDoubleClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            (e.target as HTMLInputElement).blur();
          }
          if (e.key === "Escape") {
            e.preventDefault();
            setRename(null);
          }
        }}
        onBlur={(e) => {
          const next = e.target.value.trim();
          setRename(null);
          if (next && next !== value) onCommit(next);
        }}
      />
    );
  }

  function sessionRow(c: Customer, s: SavedSession, indent: number) {
    if (q && !sessionBlob(c, s).includes(q)) return null;
    const selected = sel?.k === "s" && sel.sid === s.id;
    const dropKey = `sess:${s.id}`;
    return (
      <div
        className={`session-row ${selected ? "sel" : ""} ${dropOn === dropKey ? "drop-on" : ""}`}
        key={s.id}
        tabIndex={0}
        style={{ paddingLeft: 10 + indent * 12 }}
        draggable={!isRenaming({ k: "s", id: c.id, sid: s.id })}
        onDragStart={(e) => {
          setTreeDrag({ kind: "session", customerId: c.id, sessionId: s.id }, e.dataTransfer);
          e.currentTarget.classList.add("dragging");
        }}
        onDragEnd={(e) => {
          e.currentTarget.classList.remove("dragging");
          clearTreeDrag();
          setDropOn(null);
        }}
        title="Click to select · double-click to connect · drag onto a client or folder to move"
        onClick={() => setSel({ k: "s", id: c.id, sid: s.id })}
        onDoubleClick={() => onOpen(c, s)}
        {...dropHandlers(dropKey, c.id, s.folder || "")}
        onContextMenu={(e) => {
          e.preventDefault();
          setSel({ k: "s", id: c.id, sid: s.id });
          setMenu({
            x: e.clientX,
            y: e.clientY,
            items: [
              { label: "Connect", run: () => onOpen(c, s) },
              { label: "Rename", run: () => setRename({ k: "s", id: c.id, sid: s.id }) },
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
        {label(s.name, { k: "s", id: c.id, sid: s.id }, (name) => { void onRenameSession(s, name); })}
        <small>{s.kind}</small>
      </div>
    );
  }

  function customerMenu(c: Customer): MenuItem[] {
    return [
      { label: "Rename", run: () => setRename({ k: "c", id: c.id }) },
      { label: "New session", run: () => onNewSession(c) },
      { label: "New folder", run: () => addEmptyFolder(c) },
      { label: "—" },
      { label: "Delete client", danger: true, run: () => { void onDeleteCustomer(c); } },
    ];
  }

  function renderNode(c: Customer, node: FolderNode, indent: number): ReactNode {
    return (
      <>
        {node.children.map((child) => {
          if (q && !nodeMatches(c, child, q)) return null;
          const fid = `${c.id}:${child.path}`;
          const shown = q ? true : foldOpen[fid] !== false;
          const on = activeWorkset === worksetKey(c.id, child.path);
          const selected = sel?.k === "f" && sel.id === c.id && sel.path === child.path;
          return (
            <div key={fid}>
              <div
                className={`folder-row ${on ? "on" : ""} ${selected ? "sel" : ""} ${dropOn === fid ? "drop-on" : ""}`}
                style={{ paddingLeft: 10 + indent * 12 }}
                tabIndex={0}
                draggable={!isRenaming({ k: "f", id: c.id, path: child.path })}
                onDragStart={(e) => {
                  setTreeDrag({ kind: "folder", customerId: c.id, folder: child.path }, e.dataTransfer);
                }}
                onDragEnd={() => { clearTreeDrag(); setDropOn(null); }}
                onClick={() => {
                  setSel({ k: "f", id: c.id, path: child.path });
                  onSelectFolder(c, child.path);
                }}
                {...dropHandlers(fid, c.id, child.path)}
                onContextMenu={(e) => {
                  e.preventDefault();
                  setSel({ k: "f", id: c.id, path: child.path });
                  setMenu({
                    x: e.clientX,
                    y: e.clientY,
                    items: [
                      { label: "Show this folder’s tabs", run: () => onSelectFolder(c, child.path) },
                      { label: "Connect all in folder", run: () => onOpenFolder(c, child.path, collectSessions(child)) },
                      { label: "New session in folder", run: () => onNewSession(c, child.path) },
                      { label: "New folder inside", run: () => addEmptyFolder(c, child.path) },
                      { label: "Rename", run: () => setRename({ k: "f", id: c.id, path: child.path }) },
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
                        saveEmptyFolders(next);
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
                {label(child.name, { k: "f", id: c.id, path: child.path }, (name) => {
                  const parent = child.path.includes("/") ? child.path.slice(0, child.path.lastIndexOf("/")) : "";
                  void onRenameFolder(c, child.path, parent ? `${parent}/${name}` : name);
                })}
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

  const visibleCustomers = customers.filter((c) => {
    if (!q) return true;
    if (c.name.toLowerCase().includes(q)) return true;
    const tree = trees.get(c.id)!;
    return nodeMatches(c, tree, q) || tree.sessions.some((s) => sessionBlob(c, s).includes(q));
  });

  return (
    <aside className="sidebar explorer" tabIndex={-1} onKeyDown={onExplorerKey}>
      <div
        className="frame-head"
        data-frame="sessions"
        draggable
        onDragStart={() => onDockStart?.()}
        title="Drag to dock this session manager on another edge"
      >
        <span>Sessions</span>
        <span className="row">
          <button type="button" className="ghost" onClick={onQuickConnect} onMouseDown={(e) => e.stopPropagation()}>Quick</button>
          <button
            type="button"
            className="ghost"
            title="New session in the selected client or folder"
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => {
              const t = selectedTarget();
              if (t) onNewSession(t.c, t.folder || undefined);
              else onNewCustomer();
            }}
          >+ Session</button>
          <button
            type="button"
            className="ghost"
            title="New folder in the selected client"
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => {
              const t = selectedTarget();
              if (t) addEmptyFolder(t.c, t.folder);
            }}
          >+ Folder</button>
          <button type="button" className="ghost" onClick={onNewCustomer} onMouseDown={(e) => e.stopPropagation()}>+ Client</button>
          <button
            type="button"
            className="ghost frame-hide"
            title="Hide session manager (⌘⇧S)"
            onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); }}
            onClick={(e) => { e.stopPropagation(); onHide(); }}
          >Hide</button>
        </span>
      </div>
      <div className="ex-tools">
        <input
          className="ex-filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by client, folder, session…"
        />
      </div>
      {visibleCustomers.length === 0 && (
        <p className="ex-empty">{customers.length === 0 ? "No clients yet. + Client to add one." : "No matches."}</p>
      )}
      {visibleCustomers.map((c) => {
        const shown = q ? true : open[c.id] !== false;
        const tree = trees.get(c.id)!;
        const rootOn = activeWorkset === worksetKey(c.id, "");
        const dropKey = `cust:${c.id}`;
        const selected = sel?.k === "c" && sel.id === c.id;
        return (
          <div className="customer" key={c.id}>
            <header
              className={`${rootOn ? "on" : ""} ${selected ? "sel" : ""} ${dropOn === dropKey ? "drop-on" : ""}`}
              tabIndex={0}
              onClick={() => {
                setSel({ k: "c", id: c.id });
                onSelectFolder(c, "");
              }}
              {...dropHandlers(dropKey, c.id, "")}
              onContextMenu={(e) => {
                e.preventDefault();
                setSel({ k: "c", id: c.id });
                setMenu({ x: e.clientX, y: e.clientY, items: customerMenu(c) });
              }}
            >
              <button
                className="fold-chev"
                onClick={(e) => { e.stopPropagation(); setOpen({ ...open, [c.id]: !shown }); }}
                aria-label={shown ? "Collapse" : "Expand"}
              >{shown ? "▾" : "▸"}</button>
              <span className="dot" style={{ background: c.color }} />
              {label(c.name, { k: "c", id: c.id }, (name) => { void onRenameCustomer(c, name); })}
              <small style={{ marginLeft: "auto", color: "var(--muted)" }}>{c.sessions.length}</small>
            </header>
            {shown && (
              <>
                {renderNode(c, tree, 1)}
                {tree.sessions.map((s) => sessionRow(c, s, 1))}
              </>
            )}
          </div>
        );
      })}
      {menu && <ContextMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => setMenu(null)} />}
    </aside>
  );
}
