import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Customer, SavedSession } from "../types";
import {
  buildTree,
  collectSessions,
  loadEmptyFolders,
  moveDestinations,
  normFolder,
  saveEmptyFolders,
  type FolderNode,
} from "../sessionTree";

function destValue(customerId: number, folder: string) {
  return JSON.stringify({ c: customerId, f: folder });
}

function InlineName({
  value,
  onSave,
}: {
  value: string;
  onSave: (next: string) => Promise<void>;
}) {
  const [on, setOn] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => { setDraft(value); }, [value]);

  async function commit() {
    const next = draft.trim();
    setOn(false);
    if (!next || next === value) {
      setDraft(value);
      return;
    }
    await onSave(next);
  }

  if (!on) {
    return (
      <button type="button" className="st-name" title="Click to rename" onClick={() => setOn(true)}>
        {value}
      </button>
    );
  }
  return (
    <input
      className="st-name-in"
      value={draft}
      autoFocus
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => { void commit(); }}
      onKeyDown={(e) => {
        if (e.key === "Enter") { e.preventDefault(); void commit(); }
        if (e.key === "Escape") { setDraft(value); setOn(false); }
      }}
    />
  );
}

export default function SessionTreeEditor({
  reloadToken,
  onChanged,
}: {
  reloadToken?: string;
  onChanged?: () => void;
}) {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [empty, setEmpty] = useState(loadEmptyFolders);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState("");

  async function load() {
    setErr("");
    try {
      setCustomers(await api<Customer[]>("/api/customers"));
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => { void load(); }, [reloadToken]);

  async function after() {
    await load();
    onChanged?.();
  }

  const dests = useMemo(() => moveDestinations(customers, empty), [customers, empty]);
  const q = filter.trim().toLowerCase();

  function addFolder(c: Customer, parent = "") {
    const name = window.prompt("Folder name", parent ? "" : "Site");
    if (!name?.trim()) return;
    const path = parent ? `${normFolder(parent)}/${normFolder(name)}` : normFolder(name);
    const next = { ...empty, [String(c.id)]: [...(empty[String(c.id)] || []), path] };
    setEmpty(next);
    saveEmptyFolders(next);
  }

  async function renameCustomer(c: Customer, name: string) {
    await api(`/api/customers/${c.id}`, {
      method: "PUT",
      body: JSON.stringify({ name, color: c.color, notes: c.notes }),
    });
    await after();
  }

  async function renameFolder(c: Customer, from: string, to: string) {
    await api("/api/folders/rename", {
      method: "POST",
      body: JSON.stringify({ customer_id: c.id, from_folder: from, to_folder: normFolder(to) }),
    });
    const cid = String(c.id);
    const mapped = (empty[cid] || []).map((f) => {
      if (f === from) return normFolder(to);
      if (f.startsWith(from + "/")) return `${normFolder(to)}${f.slice(from.length)}`;
      return f;
    });
    const next = { ...empty, [cid]: mapped };
    setEmpty(next);
    saveEmptyFolders(next);
    await after();
  }

  async function deleteFolder(c: Customer, path: string) {
    const tree = buildTree(c.sessions, empty[String(c.id)] || []);
    const node = findNode(tree, path);
    const n = node ? collectSessions(node).length : 0;
    if (n && !window.confirm(`Move ${n} session${n === 1 ? "" : "s"} out of ${path}?`)) return;
    const parent = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
    if (n) {
      await api("/api/folders/rename", {
        method: "POST",
        body: JSON.stringify({ customer_id: c.id, from_folder: path, to_folder: parent }),
      });
    }
    const cid = String(c.id);
    const next = {
      ...empty,
      [cid]: (empty[cid] || []).filter((f) => f !== path && !f.startsWith(path + "/")),
    };
    setEmpty(next);
    saveEmptyFolders(next);
    await after();
  }

  async function moveSession(s: SavedSession, raw: string) {
    const d = JSON.parse(raw) as { c: number; f: string };
    if (d.c === s.customer_id && (d.f || "") === (s.folder || "")) return;
    await api(`/api/sessions/${s.id}`, {
      method: "PUT",
      body: JSON.stringify({ customer_id: d.c, folder: d.f }),
    });
    await after();
  }

  async function renameSession(s: SavedSession, name: string) {
    await api(`/api/sessions/${s.id}`, { method: "PUT", body: JSON.stringify({ name }) });
    await after();
  }

  async function deleteSession(s: SavedSession) {
    if (!window.confirm(`Delete session ${s.name}?`)) return;
    await api(`/api/sessions/${s.id}`, { method: "DELETE" });
    await after();
  }

  async function deleteCustomer(c: Customer) {
    const n = c.sessions.length;
    if (!window.confirm(`Delete ${c.name}${n ? ` and ${n} session${n === 1 ? "" : "s"}` : ""}?`)) return;
    await api(`/api/customers/${c.id}`, { method: "DELETE" });
    await after();
  }

  async function newCustomer() {
    const name = window.prompt("Client name");
    if (!name?.trim()) return;
    await api("/api/customers", {
      method: "POST",
      body: JSON.stringify({ name: name.trim(), color: "#ffb020", notes: "" }),
    });
    await after();
  }

  function visible(c: Customer, s: SavedSession) {
    if (!q) return true;
    const blob = `${c.name} ${s.name} ${s.host} ${s.folder} ${s.kind}`.toLowerCase();
    return blob.includes(q);
  }

  function renderNode(c: Customer, node: FolderNode, indent: number) {
    return (
      <>
        {node.children.map((child) => {
          const kids = collectSessions(child);
          const show = !q || kids.some((s) => visible(c, s)) || child.path.toLowerCase().includes(q);
          if (!show) return null;
          return (
            <div key={`${c.id}:${child.path}`}>
              <div className="st-row st-folder" style={{ paddingLeft: 12 + indent * 14 }}>
                <InlineName value={child.name} onSave={(name) => {
                  const parent = child.path.includes("/") ? child.path.slice(0, child.path.lastIndexOf("/")) : "";
                  return renameFolder(c, child.path, parent ? `${parent}/${name}` : name);
                }} />
                <small>{kids.length}</small>
                <button type="button" className="ghost" onClick={() => addFolder(c, child.path)}>Folder inside</button>
                <button type="button" className="ghost" onClick={() => void deleteFolder(c, child.path)}>Delete</button>
              </div>
              {renderNode(c, child, indent + 1)}
              {child.sessions.filter((s) => visible(c, s)).map((s) => sessionRow(c, s, indent + 1))}
            </div>
          );
        })}
      </>
    );
  }

  function sessionRow(c: Customer, s: SavedSession, indent: number) {
    return (
      <div className="st-row" key={s.id} style={{ paddingLeft: 12 + indent * 14 }}>
        <InlineName value={s.name} onSave={(name) => renameSession(s, name)} />
        <small>{s.kind}{s.host ? ` · ${s.host}` : ""}</small>
        <select
          className="st-move"
          value={destValue(s.customer_id, s.folder || "")}
          onChange={(e) => void moveSession(s, e.target.value)}
          title="Move to another client or folder"
        >
          {dests.map((d) => (
            <option key={destValue(d.customerId, d.folder)} value={destValue(d.customerId, d.folder)}>
              {d.label}
            </option>
          ))}
        </select>
        <button type="button" className="ghost" onClick={() => void deleteSession(s)}>Delete</button>
      </div>
    );
  }

  return (
    <div className="st-editor">
      <div className="row" style={{ marginBottom: 8 }}>
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by client, folder, host…"
          style={{ flex: 1, minWidth: 160 }}
        />
        <button type="button" className="primary" onClick={() => void newCustomer()}>New client</button>
      </div>
      {err && <p className="stat" style={{ color: "var(--danger)" }}>{err}</p>}
      {customers.length === 0 && !err && (
        <p style={{ color: "var(--muted)", margin: 0 }}>No clients yet. Add one, or import a file below.</p>
      )}
      {customers.map((c) => {
        const tree = buildTree(c.sessions, empty[String(c.id)] || []);
        const showCust = !q || c.name.toLowerCase().includes(q) || c.sessions.some((s) => visible(c, s));
        if (!showCust) return null;
        return (
          <div className="st-cust" key={c.id}>
            <div className="st-row st-head">
              <span className="dot" style={{ background: c.color }} />
              <InlineName value={c.name} onSave={(name) => renameCustomer(c, name)} />
              <small>{c.sessions.length}</small>
              <button type="button" className="ghost" onClick={() => addFolder(c)}>New folder</button>
              <button type="button" className="ghost" onClick={() => void deleteCustomer(c)}>Delete</button>
            </div>
            {renderNode(c, tree, 1)}
            {tree.sessions.filter((s) => visible(c, s)).map((s) => sessionRow(c, s, 1))}
          </div>
        );
      })}
    </div>
  );
}

function findNode(node: FolderNode, path: string): FolderNode | null {
  if (node.path === path) return node;
  for (const child of node.children) {
    const hit = findNode(child, path);
    if (hit) return hit;
  }
  return null;
}
