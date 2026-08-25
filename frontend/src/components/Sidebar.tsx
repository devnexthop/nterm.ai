import type { Customer, SavedSession } from "../types";
import { useState } from "react";

export default function Sidebar({
  customers,
  onOpen,
  onNewCustomer,
  onNewSession,
  onEditSession,
}: {
  customers: Customer[];
  onOpen: (c: Customer, s: SavedSession) => void;
  onNewCustomer: () => void;
  onNewSession: (c: Customer) => void;
  onEditSession: (c: Customer, s: SavedSession) => void;
}) {
  const [open, setOpen] = useState<Record<number, boolean>>({});
  return (
    <aside className="sidebar">
      <div className="side-head">
        Customers
        <button className="ghost" onClick={onNewCustomer}>+ New</button>
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
                  <div className="session-row" key={s.id} onClick={() => onOpen(c, s)} onContextMenu={(e) => { e.preventDefault(); onEditSession(c, s); }}>
                    <span>{s.kind === "simulator" ? "▣" : s.kind === "local" ? "⌘" : "↣"}</span>
                    <span>{s.name}</span>
                    <small>{s.device_type.replace("_", " ")}</small>
                  </div>
                ))}
                <div className="session-row" onClick={() => onNewSession(c)}>+ session</div>
              </>
            )}
          </div>
        );
      })}
    </aside>
  );
}
