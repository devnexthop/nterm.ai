import { useState, type MouseEvent } from "react";
import type { MenuItem, Snippet } from "../types";
import { sendToTab } from "./TerminalPane";
import ContextMenu from "./ContextMenu";

const PACKS = [
  { id: "auto", label: "Auto (this session)" },
  { id: "cisco-essentials", label: "Cisco" },
  { id: "palo-essentials", label: "Palo Alto" },
  { id: "forti-essentials", label: "Fortinet" },
  { id: "juniper-essentials", label: "Juniper" },
  { id: "user-snippets", label: "My chips" },
  { id: "all", label: "All vendors" },
];

export default function SnippetBar({
  snippets,
  pack,
  onPack,
  tabId,
  onAdd,
  onEdit,
  onDelete,
}: {
  snippets: Snippet[];
  pack: string;
  onPack: (id: string) => void;
  tabId?: string;
  onAdd: () => void;
  onEdit: (s: Snippet) => void;
  onDelete: (s: Snippet) => void;
}) {
  const [menu, setMenu] = useState<{ x: number; y: number; items: MenuItem[] } | null>(null);

  function send(s: Snippet) {
    if (!tabId) return;
    const cmd = s.command.endsWith("\n") ? s.command : s.command + "\n";
    sendToTab(tabId, cmd);
  }

  function chipMenu(e: MouseEvent, s: Snippet) {
    e.preventDefault();
    e.stopPropagation();
    const items: MenuItem[] = [
      { label: "Send to session", run: () => send(s) },
    ];
    if (s.editable) {
      items.push({ label: "Edit chip", run: () => onEdit(s) });
      items.push({ label: "Delete", danger: true, run: () => onDelete(s) });
    } else {
      items.push({ label: "Copy into my chips", run: () => onEdit({ ...s, id: undefined, editable: true }) });
    }
    setMenu({ x: e.clientX, y: e.clientY, items });
  }

  return (
    <div className="snippets">
      <select value={pack} onChange={(e) => onPack(e.target.value)} title="Vendor pack">
        {PACKS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
      </select>
      {snippets.map((s) => (
        <button
          key={`${s.extension}-${s.id || s.name}`}
          className={`chip ${s.editable ? "mine" : ""}`}
          title={s.command}
          onClick={() => send(s)}
          onContextMenu={(e) => chipMenu(e, s)}
        >
          {s.name}
        </button>
      ))}
      <button className="chip add" onClick={onAdd}>+ chip</button>
      {menu && <ContextMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => setMenu(null)} />}
    </div>
  );
}
