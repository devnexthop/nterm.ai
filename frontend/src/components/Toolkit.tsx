import { useEffect, useState } from "react";
import { api } from "../api";
import type { Extension, Finding } from "../types";

export default function Toolkit() {
  const [status, setStatus] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [exts, setExts] = useState<Extension[]>([]);
  const [cidr, setCidr] = useState("10.10.0.0/22");
  const [split, setSplit] = useState("24");
  const [calc, setCalc] = useState<any>(null);
  const [cfg, setCfg] = useState("");
  const [dtype, setDtype] = useState("cisco_ios");
  const [findings, setFindings] = useState<Finding[]>([]);
  const [err, setErr] = useState("");

  async function refresh() {
    setStatus(await api("/api/toolkit"));
    setEvents(await api("/api/toolkit/syslog/events"));
    setExts(await api("/api/extensions"));
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, []);

  async function toggle(name: string, enabled: boolean, extra: any = {}) {
    setErr("");
    try {
      await api(`/api/toolkit/${name}`, {
        method: "POST",
        body: JSON.stringify({ enabled, ...extra }),
      });
      await refresh();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function upload(f: File) {
    const fd = new FormData();
    fd.append("file", f);
    await fetch("/api/toolkit/tftp/files", { method: "POST", body: fd });
    refresh();
  }

  if (!status) return <div className="page">Loading toolkit…</div>;

  return (
    <div className="page">
      <h1>Architect toolkit</h1>
      <p style={{ color: "var(--muted)", maxWidth: 720 }}>
        Built-in Kiwi / TFTPD32-style services. Enable what you need for a lab or a customer cutover:
        syslog receiver, TFTP drop, DHCP with option 66/67/150, config analyzers, and a subnet pad.
      </p>
      {err && <p className="sev-high">{err}</p>}

      <div className="grid-2">
        <ServiceCard
          title="Syslog server"
          hint="Point `logging host <relay-ip>` / PAN syslog / Forti syslog here. Default UDP 514."
          running={status.syslog.running}
          onStart={() => toggle("syslog", true, { port: status.syslog.port })}
          onStop={() => toggle("syslog", false)}
        >
          <div className="field">
            <span>Port</span>
            <input defaultValue={status.syslog.port} id="syslog-port" />
          </div>
          <button className="ghost" onClick={() => {
            const port = Number((document.getElementById("syslog-port") as HTMLInputElement).value);
            toggle("syslog", true, { port });
          }}>Apply port</button>
          <button className="ghost" onClick={() => api("/api/toolkit/syslog/events", { method: "DELETE" }).then(refresh)}>Clear</button>
          <table className="table">
            <thead><tr><th>Src</th><th>Sev</th><th>Message</th></tr></thead>
            <tbody>
              {events.slice(-12).map((e) => (
                <tr key={e.id}><td>{e.source_ip}</td><td>{e.severity}</td><td>{e.message.slice(0, 80)}</td></tr>
              ))}
            </tbody>
          </table>
        </ServiceCard>

        <ServiceCard
          title="TFTP server"
          hint="Drop IOS images and configs. Devices: copy tftp://&lt;relay-ip&gt;/file flash:"
          running={status.tftp.running}
          onStart={() => toggle("tftp", true)}
          onStop={() => toggle("tftp", false)}
        >
          <p>Root: <code>{status.tftp.root}</code></p>
          <input type="file" onChange={(e) => e.target.files && upload(e.target.files[0])} />
          <ul>
            {(status.tftp.files || []).map((f: any) => (
              <li key={f.name}>{f.name} · {f.size} B</li>
            ))}
          </ul>
        </ServiceCard>

        <ServiceCard
          title="DHCP server"
          hint="Lab / ZTP scopes. Option 66/67/150 included for phones and zero-touch switches. Needs UDP 67 on the wire."
          running={status.dhcp.running}
          onStart={() => toggle("dhcp", true, { config: status.dhcp.config })}
          onStop={() => toggle("dhcp", false)}
        >
          {["pool_start", "pool_end", "router", "dns", "tftp_server", "bootfile", "server_id"].map((k) => (
            <div className="field" key={k}>
              <span>{k.replace("_", " ")}</span>
              <input
                defaultValue={status.dhcp.config[k]}
                onBlur={(e) => { status.dhcp.config[k] = e.target.value; }}
              />
            </div>
          ))}
          <button className="ghost" onClick={() => toggle("dhcp", true, { config: status.dhcp.config })}>Save & start</button>
          <table className="table">
            <thead><tr><th>MAC</th><th>IP</th><th>State</th></tr></thead>
            <tbody>
              {(status.dhcp.leases || []).map((l: any) => (
                <tr key={l.id}><td>{l.mac}</td><td>{l.ip}</td><td>{l.state}</td></tr>
              ))}
            </tbody>
          </table>
        </ServiceCard>

        <div className="card">
          <h3>Subnet calculator</h3>
          <p>CIDR, wildcard, VLSM split — the napkin math you do before a change window.</p>
          <div className="row">
            <input value={cidr} onChange={(e) => setCidr(e.target.value)} />
            <input value={split} onChange={(e) => setSplit(e.target.value)} style={{ width: 80 }} />
            <button className="primary" onClick={async () => {
              setCalc(await api("/api/calc/subnet", { method: "POST", body: JSON.stringify({ cidr, split: Number(split) || null }) }));
            }}>Calc</button>
          </div>
          {calc && (
            <pre style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
{`network ${calc.network}/${calc.prefix}
mask ${calc.netmask}  wildcard ${calc.wildcard}
hosts ${calc.first_host} – ${calc.last_host} (${calc.usable_hosts})`}
            </pre>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Config analyzer</h3>
        <p>Paste a `show run`, PAN set output, or Forti `show`. Uses the built-in Cisco / PAN / Forti auditors.</p>
        <div className="row">
          <select value={dtype} onChange={(e) => setDtype(e.target.value)}>
            <option value="cisco_ios">Cisco IOS</option>
            <option value="paloalto">PAN-OS</option>
            <option value="fortinet">FortiOS</option>
            <option value="generic">Generic</option>
          </select>
          <button className="primary" onClick={async () => {
            const res = await api<{ findings: Finding[] }>("/api/analyze", {
              method: "POST",
              body: JSON.stringify({ device_type: dtype, text: cfg }),
            });
            setFindings(res.findings);
          }}>Analyze</button>
        </div>
        <textarea value={cfg} onChange={(e) => setCfg(e.target.value)} rows={10} style={{ width: "100%", marginTop: 8, fontFamily: "var(--mono)" }} />
        <ul>
          {findings.map((f, i) => (
            <li key={i}><strong className={`sev-${f.severity}`}>{f.severity}</strong> — {f.title}: {f.detail}</li>
          ))}
        </ul>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Extensions</h3>
        <p>All of these ship built-in. Toggle what you want. Paste a JSON manifest to add snippets or an analyzer — no code.</p>
        {exts.map((e) => (
          <div className="row" key={e.id} style={{ marginBottom: 8 }}>
            <strong>{e.name}</strong>
            <span style={{ color: "var(--muted)" }}>{e.kind} · {e.description}</span>
            <button className="ghost" onClick={() => api(`/api/extensions/${e.id}/toggle`, { method: "POST", body: JSON.stringify({ enabled: !e.enabled }) }).then(refresh)}>
              {e.enabled ? "Enabled" : "Disabled"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function ServiceCard({ title, hint, running, onStart, onStop, children }: any) {
  return (
    <div className="card">
      <div className="row">
        <h3>{title}</h3>
        <span className={running ? "status-on" : "status-off"}>{running ? "running" : "stopped"}</span>
        {running ? <button className="ghost" onClick={onStop}>Stop</button> : <button className="primary" onClick={onStart}>Start</button>}
      </div>
      <p>{hint}</p>
      {children}
    </div>
  );
}
