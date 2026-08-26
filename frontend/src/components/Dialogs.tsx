import { useEffect, useState } from "react";
import { api } from "../api";
import type { Credential, Customer, SavedSession, SerialPort } from "../types";

const DEVICES = [
  ["cisco_ios", "Cisco IOS/XE"],
  ["cisco_nxos", "Cisco NX-OS"],
  ["cisco_asa", "Cisco ASA"],
  ["paloalto", "Palo Alto"],
  ["fortinet", "Fortinet"],
  ["juniper", "Juniper"],
  ["linux", "Linux"],
  ["generic", "Generic"],
] as const;

function defaultPort(kind: string, current: number) {
  if (kind === "telnet") return 23;
  if (kind === "ssh") return 22;
  if (kind === "serial") return current || 0;
  return current || 22;
}

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
    <div className="palette-back" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <input
          autoFocus
          placeholder="Jump to a session, Do bar, subnet, Monitor…"
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
  onSave: (body: Record<string, unknown>) => Promise<void>;
}) {
  const [creds, setCreds] = useState<Credential[]>([]);
  const [ports, setPorts] = useState<SerialPort[]>([]);
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
    credential_id: session?.credential_id || null as number | null,
    baud: session?.baud || 9600,
    save_as_credential: "",
  });

  useEffect(() => {
    api<Credential[]>("/api/credentials").then(setCreds);
    api<SerialPort[]>("/api/serial/ports").then(setPorts).catch(() => setPorts([]));
  }, []);

  function setKind(kind: string) {
    setForm({ ...form, kind, port: defaultPort(kind, form.port) });
  }

  const vaulted = Boolean(form.credential_id);
  const picked = creds.find((c) => c.id === form.credential_id);

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <h3>{session ? "Edit session" : "New session"}</h3>
        <div className="field"><span>Customer</span>
          <select value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: Number(e.target.value) })}>
            {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="field"><span>Name</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
        <div className="row">
          <div className="field"><span>Kind</span>
            <select value={form.kind} onChange={(e) => setKind(e.target.value)}>
              <option value="ssh">SSH</option>
              <option value="telnet">Telnet</option>
              <option value="serial">Serial</option>
              <option value="local">Local shell</option>
              <option value="simulator">Simulator</option>
            </select>
          </div>
          <div className="field"><span>Device</span>
            <select value={form.device_type} onChange={(e) => setForm({ ...form, device_type: e.target.value })}>
              {DEVICES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
        </div>
        {form.kind === "serial" ? (
          <div className="row">
            <div className="field" style={{ flex: 1 }}><span>Port</span>
              {ports.length ? (
                <select value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })}>
                  <option value="">Select a serial port</option>
                  {ports.map((p) => <option key={p.device} value={p.device}>{p.device} · {p.description}</option>)}
                </select>
              ) : (
                <input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} placeholder="/dev/cu.usbserial-* or COM3" />
              )}
            </div>
            <div className="field"><span>Baud</span>
              <input type="number" value={form.baud} onChange={(e) => setForm({ ...form, baud: Number(e.target.value) })} />
            </div>
          </div>
        ) : (
          <div className="row">
            <div className="field" style={{ flex: 1 }}><span>Host</span><input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} /></div>
            <div className="field"><span>TCP port</span><input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: Number(e.target.value) })} /></div>
          </div>
        )}
        <div className="field"><span>Saved credential</span>
          <select
            value={form.credential_id || ""}
            onChange={(e) => {
              const id = e.target.value ? Number(e.target.value) : null;
              const c = creds.find((x) => x.id === id);
              setForm({ ...form, credential_id: id, username: c?.username || form.username });
            }}
          >
            <option value="">Type username / password below</option>
            {creds.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.username || "no user"}</option>)}
          </select>
        </div>
        {vaulted && <p className="hint">Password comes from the vault{picked ? ` (${picked.name})` : ""}. Secrets are never returned by GET.</p>}
        <div className="field"><span>Username</span><input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></div>
        {!vaulted && (
          <>
            <div className="field"><span>Password {session?.has_password ? "(stored — leave blank to keep)" : ""}</span>
              <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </div>
            <div className="field"><span>Enable password</span>
              <input type="password" value={form.enable_password} onChange={(e) => setForm({ ...form, enable_password: e.target.value })} />
            </div>
            <div className="field"><span>Also save as credential</span>
              <input value={form.save_as_credential} onChange={(e) => setForm({ ...form, save_as_credential: e.target.value })} placeholder="Lab TACACS" />
            </div>
          </>
        )}
        <div className="field"><span>Notes</span><input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
        <label className="row"><input type="checkbox" checked={form.logging_enabled} onChange={(e) => setForm({ ...form, logging_enabled: e.target.checked })} /> Save session text log</label>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="primary" onClick={() => onSave({ ...form, save_as_credential: form.save_as_credential || undefined, credential_id: form.credential_id || undefined })}>Save</button>
          <button className="ghost" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

export function QuickConnect({
  customers,
  onClose,
  onConnect,
}: {
  customers: Customer[];
  onClose: () => void;
  onConnect: (c: Customer, s: SavedSession, keep: boolean) => void;
}) {
  const [creds, setCreds] = useState<Credential[]>([]);
  const [keep, setKeep] = useState(true);
  const [form, setForm] = useState({
    customer_id: customers[0]?.id,
    name: "",
    kind: "ssh",
    device_type: "cisco_ios",
    host: "",
    port: 22,
    username: "",
    password: "",
    enable_password: "",
    credential_id: null as number | null,
    baud: 9600,
  });

  useEffect(() => {
    api<Credential[]>("/api/credentials").then(setCreds);
  }, []);

  async function connect() {
    const name = form.name || form.host || "Quick connect";
    const session = await api<SavedSession>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ ...form, name, logging_enabled: true, notes: "", credential_id: form.credential_id || undefined }),
    });
    const cust = customers.find((c) => c.id === form.customer_id) || customers[0];
    onConnect(cust, session, keep);
    onClose();
  }

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Quick connect</h3>
        <p className="hint">SSH, Telnet, or Serial — like PuTTY, then optionally keep the session.</p>
        <div className="field"><span>Customer</span>
          <select value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: Number(e.target.value) })}>
            {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="row">
          <div className="field"><span>Kind</span>
            <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value, port: defaultPort(e.target.value, form.port) })}>
              <option value="ssh">SSH</option>
              <option value="telnet">Telnet</option>
              <option value="serial">Serial</option>
              <option value="simulator">Simulator</option>
            </select>
          </div>
          <div className="field"><span>Device</span>
            <select value={form.device_type} onChange={(e) => setForm({ ...form, device_type: e.target.value })}>
              {DEVICES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
        </div>
        <div className="row">
          <div className="field" style={{ flex: 1 }}><span>{form.kind === "serial" ? "Serial port" : "Host"}</span>
            <input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} placeholder={form.kind === "serial" ? "/dev/cu.usbserial-*" : "10.1.1.1"} />
          </div>
          {form.kind === "serial" ? (
            <div className="field"><span>Baud</span><input type="number" value={form.baud} onChange={(e) => setForm({ ...form, baud: Number(e.target.value) })} /></div>
          ) : (
            <div className="field"><span>Port</span><input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: Number(e.target.value) })} /></div>
          )}
        </div>
        <div className="field"><span>Saved credential</span>
          <select value={form.credential_id || ""} onChange={(e) => {
            const id = e.target.value ? Number(e.target.value) : null;
            const c = creds.find((x) => x.id === id);
            setForm({ ...form, credential_id: id, username: c?.username || form.username });
          }}>
            <option value="">None</option>
            {creds.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="field"><span>Username</span><input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></div>
        {!form.credential_id && (
          <div className="field"><span>Password</span><input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
        )}
        <label className="row"><input type="checkbox" checked={keep} onChange={(e) => setKeep(e.target.checked)} /> Keep in sidebar</label>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="primary" onClick={connect}>Connect</button>
          <button className="ghost" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

export function CredentialForm({
  cred,
  onClose,
  onSave,
}: {
  cred?: Credential;
  onClose: () => void;
  onSave: (body: Record<string, unknown>) => Promise<void>;
}) {
  const [form, setForm] = useState({
    name: cred?.name || "",
    username: cred?.username || "",
    password: "",
    enable_password: "",
    device_type: cred?.device_type || "",
    notes: cred?.notes || "",
  });
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{cred ? "Edit credential" : "New credential"}</h3>
        <div className="field"><span>Name</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Lab TACACS" /></div>
        <div className="field"><span>Username</span><input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></div>
        <div className="field"><span>Password {cred?.has_password ? "(stored — leave blank to keep)" : ""}</span>
          <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </div>
        <div className="field"><span>Enable password</span>
          <input type="password" value={form.enable_password} onChange={(e) => setForm({ ...form, enable_password: e.target.value })} />
        </div>
        <div className="field"><span>Device hint</span>
          <select value={form.device_type} onChange={(e) => setForm({ ...form, device_type: e.target.value })}>
            <option value="">Any</option>
            {DEVICES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
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

export function SnippetForm({
  snippet,
  defaultVendor,
  onClose,
  onSave,
}: {
  snippet?: { id?: string; name: string; command: string; device_types?: string[] };
  defaultVendor?: string;
  onClose: () => void;
  onSave: (body: { id?: string; name: string; command: string; device_types: string[] }) => Promise<void>;
}) {
  const [name, setName] = useState(snippet?.name || "");
  const [command, setCommand] = useState(snippet?.command || "");
  const [vendor, setVendor] = useState((snippet?.device_types && snippet.device_types[0]) || defaultVendor || "");
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{snippet?.id ? "Edit chip" : "New chip"}</h3>
        <p className="hint">One-click command for the bar under the session. Pick a vendor or leave Any.</p>
        <div className="field"><span>Label</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Int brief" /></div>
        <div className="field"><span>Command</span>
          <textarea value={command} onChange={(e) => setCommand(e.target.value)} rows={4} style={{ fontFamily: "var(--mono)" }} placeholder="show ip interface brief" />
        </div>
        <div className="field"><span>Vendor</span>
          <select value={vendor} onChange={(e) => setVendor(e.target.value)}>
            <option value="">Any vendor</option>
            {DEVICES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="primary" onClick={() => onSave({ id: snippet?.id, name, command, device_types: vendor ? [vendor] : [] })}>Save chip</button>
          <button className="ghost" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
