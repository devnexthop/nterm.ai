import { useEffect, useState } from "react";
import type { AiEvent, Customer, MenuItem, SavedSession } from "../types";
import { api } from "../api";
import ContextMenu from "./ContextMenu";

function kindMark(kind: string) {
  if (kind === "simulator") return "▣";
  if (kind === "local") return "⌘";
  if (kind === "telnet") return "T";
  if (kind === "serial") return "⌇";
  return "↣";
}

export default function Sidebar({
  customers,
  onOpen,
  onNewCustomer,
  onNewSession,
  onEditSession,
  onDuplicate,
  onVault,
  onDelete,
  onQuickConnect,
}: {
  customers: Customer[];
  onOpen: (c: Customer, s: SavedSession) => void;
  onNewCustomer: () => void;
  onNewSession: (c: Customer) => void;
  onEditSession: (c: Customer, s: SavedSession) => void;
  onDuplicate: (s: SavedSession) => void;
  onVault: (s: SavedSession) => void;
  onDelete: (s: SavedSession) => void;
  onQuickConnect: () => void;
}) {
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const [ai, setAi] = useState<Record<number, boolean>>({});
  const [events, setEvents] = useState<Record<number, AiEvent[]>>({});
  const [menu, setMenu] = useState<{ x: number; y: number; items: MenuItem[] } | null>(null);

  async function loadTrack(cid: number) {
    const rows = await api<AiEvent[]>(`/api/ai/events?customer_id=${cid}`);
    setEvents((e) => ({ ...e, [cid]: rows.slice(0, 8) }));
  }

  useEffect(() => {
    customers.forEach((c) => { if (ai[c.id]) loadTrack(c.id); });
  }, [customers.map((c) => c.id).join(","), Object.keys(ai).join(",")]);

  return (
    <aside className="sidebar">
      <div className="side-head">Sessions<span className="row">
          <button className="ghost" onClick={onQuickConnect}>Quick</button>
          <button className="ghost" onClick={onNewCustomer}>+ New</button>
        </span>
      </div>
      {customers.map((c) => {
        const shown = open[c.id] !== false;
        return (
          <div className="customer" key={c.id}>
            <header onClick={() => setOpen({ ...open, [c.id]: !shown })}>
              <span className="dot" style={{ background: c.color }} />
              <strong>{c.name}</strong>
              <small style={{ marginLeft: "auto", color: "var(--muted)" }}>{c.sessions.length}</small>
            </header>
            {shown && (
              <>
                {c.sessions.map((s) => (
                  <div
                    className="session-row"
                    key={s.id}
                    draggable
                    onDragStart={(e) => {
                      /* Drop target is the tab strip in App. The custom MIME keeps
                         this apart from tab-reordering drags, which carry none. */
                      e.dataTransfer.setData(
                        "application/x-nterm-session",
                        JSON.stringify({ customerId: c.id, sessionId: s.id }),
                      );
                      e.dataTransfer.effectAllowed = "copy";
                      e.currentTarget.classList.add("dragging");
                    }}
                    onDragEnd={(e) => e.currentTarget.classList.remove("dragging")}
                    title="Drag onto the tab strip to open"
                    onClick={() => onOpen(c, s)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      setMenu({
                        x: e.clientX,
                        y: e.clientY,
                        items: [
                          { label: "Quick connect", run: () => onOpen(c, s) },
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
                    <small>{s.kind} · {s.device_type.replace("_", " ")}</small>
                  </div>
                ))}
                <div className="session-row" onClick={() => onNewSession(c)}>+ session</div>
                <div
                  className="session-row ai-track-toggle"
                  onClick={(e) => {
                    e.stopPropagation();
                    const next = !ai[c.id];
                    setAi({ ...ai, [c.id]: next });
                    if (next) loadTrack(c.id);
                  }}
                >
                  AI track {ai[c.id] ? "▾" : "▸"}
                </div>
                {ai[c.id] && (events[c.id] || []).map((ev) => (
                  <div className="ai-track-item" key={ev.id} title={ev.commands_preview}>
                    <span className={`dec ${ev.decision}`}>{ev.decision}</span>
                    <span className="prompt">{ev.prompt}</span>
                    {ev.cache_hit && <small>cached</small>}
                  </div>
                ))}
                {ai[c.id] && !(events[c.id] || []).length && (
                  <div className="ai-track-item muted">No Do-bar asks yet</div>
                )}
              </>
            )}
          </div>
        );
      })}
      {menu && <ContextMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => setMenu(null)} />}
    </aside>
  );
}
