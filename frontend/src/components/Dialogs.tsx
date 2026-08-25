import { useEffect, useState } from "react";
import type { Customer, SavedSession } from "../types";

export function Palette({
  open,
  onClose,
  items,
}: {
  open: boolean;
  onClose: () => void;
  items: { label: string; run: () => void }[];
}) {
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  const hits = items.filter((x) => x.label.toLowerCase().includes(q.toLowerCase()));
  useEffect(() => { setI(0); }, [q, open]);
  if (!open) return null;
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <input
          autoFocus
          placeholder="Jump to a session, start a service, analyze…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            if (e.key === "ArrowDown") setI((n) => Math.min(n + 1, hits.length - 1));
            if (e.key === "ArrowUp") setI((n) => Math.max(n - 1, 0));
            if (e.key === "Enter" && hits[i]) { hits[i].run(); onClose(); }
          }}
        />
        {hits.slice(0, 12).map((h, idx) => (
          <div key={h.label} className={`hit ${idx === i ? "on" : ""}`} onClick={() => { h.run(); onClose(); }}>{h.label}</div>
        ))}
      </div>
    </div>
  );
}

export function SessionForm({
  customers,
  customer,
  session,
  onClose,
  onSave,
}: {
  customers: Customer[];
  customer?: Customer;
  session?: SavedSession;
  onClose: () => void;
  onSave: (body: any) => Promise<void>;
}) {
  const [form, setForm] = useState({
    customer_id: session?.customer_id || customer?.id || customers[0]?.id,
    name: session?.name || "",
    kind: session?.kind || "ssh",
    device_type: session?.device_type || "cisco_ios",
    host: session?.host || "",
    port: session?.port || 22,
    username: session?.username || "",
    password: "",
    enable_password: "",
    notes: session?.notes || "",
    logging_enabled: session?.logging_enabled ?? true,
    post_login: session?.post_login || "",
  });
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{session ? "Edit session" : "New session"}</h3>
        <div className="field"><span>Customer</span>
          <select value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: Number(e.target.value) })}>
            {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="field"><span>Name</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
        <div className="row">
          <div className="field"><span>Kind</span>
            <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as any })}>
              <option value="ssh">SSH</option>
              <option value="local">Local shell</option>
              <option value="simulator">Simulator</option>
            </select>
          </div>
          <div className="field"><span>Device</span>
            <select value={form.device_type} onChange={(e) => setForm({ ...form, device_type: e.target.value })}>
              <option value="cisco_ios">Cisco IOS/XE</option>
              <option value="cisco_nxos">Cisco NX-OS</option>
              <option value="cisco_asa">Cisco ASA</option>
              <option value="paloalto">Palo Alto</option>
              <option value="fortinet">Fortinet</option>
              <option value="juniper">Juniper</option>
              <option value="linux">Linux</option>
              <option value="generic">Generic</option>
            </select>
          </div>
        </div>
        <div className="row">
          <div className="field" style={{ flex: 1 }}><span>Host</span><input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} /></div>
          <div className="field"><span>Port</span><input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: Number(e.target.value) })} /></div>
        </div>
        <div className="field"><span>Username</span><input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></div>
        <div className="field"><span>Password {session?.has_password ? "(stored — leave blank to keep)" : ""}</span>
          <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </div>
        <div className="field"><span>Enable password</span>
          <input type="password" value={form.enable_password} onChange={(e) => setForm({ ...form, enable_password: e.target.value })} />
        </div>
        <div className="field"><span>Notes</span><input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
        <label className="row"><input type="checkbox" checked={form.logging_enabled} onChange={(e) => setForm({ ...form, logging_enabled: e.target.checked })} /> Save session text log</label>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="primary" onClick={() => onSave(form)}>Save</button>
          <button className="ghost" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

export function CustomerForm({ onClose, onSave }: { onClose: () => void; onSave: (name: string, color: string) => void }) {
  const [name, setName] = useState("");
  const [color, setColor] = useState("#ffb020");
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>New customer</h3>
        <div className="field"><span>Name</span><input value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div className="field"><span>Color</span><input value={color} onChange={(e) => setColor(e.target.value)} /></div>
        <div className="row">
          <button className="primary" onClick={() => onSave(name, color)}>Create</button>
          <button className="ghost" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
