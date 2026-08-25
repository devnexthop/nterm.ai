import { useEffect, useState } from "react";
import { api } from "../api";

type Tab = "calc" | "secrets" | "diff" | "migrate" | "cookbook" | "runbooks" | "lookups";

export default function Bench() {
  const [tab, setTab] = useState<Tab>("calc");
  const [status, setStatus] = useState<{ meta?: { source?: string; url?: string; ok?: boolean; error?: string; fetched_at?: string; mode?: string }; tracks?: string[] } | null>(null);
  useEffect(() => { api("/api/architect/status").then(setStatus); }, []);
  return (
    <div className="page">
      <h1>Engineer bench</h1>
      <p style={{ color: "var(--muted)", maxWidth: 760 }}>
        The pad a CCIE actually keeps open during a change window — CCNA through architect.
        Cookbooks and runbooks come from your server when a Bench feed URL is set.
      </p>
      <p style={{ color: "var(--muted)", fontSize: 12 }}>
        Source: {status?.meta?.source || "nterm-builtin"}
        {status?.meta?.url ? ` · ${status.meta.url}` : ""}
        {status?.meta?.ok === false ? ` · ${status.meta.error}` : ""}
        {status?.tracks?.length ? ` · tracks ${status.tracks.join(", ")}` : ""}
        {" · "}
        <button className="ghost" onClick={async () => {
          await api("/api/architect/refresh", { method: "POST" }).catch(() => null);
          setStatus(await api("/api/architect/status"));
        }}>Refresh feed</button>
      </p>
      <div className="row" style={{ margin: "14px 0 18px" }}>
        {([
          ["calc", "IP / ACL"],
          ["secrets", "Type-7"],
          ["diff", "Config diff"],
          ["migrate", "Firewall migrate"],
          ["cookbook", "Show cookbook"],
          ["runbooks", "Runbooks"],
          ["lookups", "DSCP / ports"],
        ] as [Tab, string][]).map(([id, label]) => (
          <button key={id} className={tab === id ? "primary" : "ghost"} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>
      {tab === "calc" && <CalcPad />}
      {tab === "secrets" && <Type7 />}
      {tab === "diff" && <DiffPad />}
      {tab === "migrate" && <MigratePad />}
      {tab === "cookbook" && <Cookbook />}
      {tab === "runbooks" && <Runbooks />}
      {tab === "lookups" && <Lookups />}
    </div>
  );
}

function CalcPad() {
  const [cidr, setCidr] = useState("10.10.0.0/22");
  const [split, setSplit] = useState("24");
  const [sub, setSub] = useState<any>(null);
  const [list, setList] = useState("10.10.1.0/24\n10.10.2.0/24\n10.10.3.0/24");
  const [sum, setSum] = useState<any>(null);
  const [acl, setAcl] = useState<any>(null);
  return (
    <div className="grid-2">
      <div className="card">
        <h3>Subnet / VLSM</h3>
        <p>Mask, wildcard, usable hosts, split for a change window.</p>
        <div className="row">
          <input value={cidr} onChange={(e) => setCidr(e.target.value)} />
          <input value={split} onChange={(e) => setSplit(e.target.value)} style={{ width: 72 }} />
          <button className="primary" onClick={async () => setSub(await api("/api/calc/subnet", { method: "POST", body: JSON.stringify({ cidr, split: Number(split) || null }) }))}>Calc</button>
        </div>
        {sub && (
          <pre className="mono-out">{`network ${sub.network}/${sub.prefix}
mask ${sub.netmask}   wildcard ${sub.wildcard}
hosts ${sub.first_host} – ${sub.last_host} (${sub.usable_hosts})`}</pre>
        )}
      </div>
      <div className="card">
        <h3>Route summarization</h3>
        <p>Collapse prefixes the way you would for a BGP aggregate or OSPF summary.</p>
        <textarea rows={5} value={list} onChange={(e) => setList(e.target.value)} style={{ width: "100%", fontFamily: "var(--mono)" }} />
        <button className="primary" onClick={async () => setSum(await api("/api/architect/summarize", { method: "POST", body: JSON.stringify({ cidrs: list }) }))}>Summarize</button>
        {sum && <pre className="mono-out">{sum.summaries.map((s: any) => `${s.cidr}  wc ${s.wildcard || ""}`).join("\n")}</pre>}
      </div>
      <div className="card">
        <h3>ACL / prefix-list from CIDR</h3>
        <p>IOS wildcard vs NX-OS prefix. Stops the 255.255.252.0 vs 0.0.3.255 mistake.</p>
        <div className="row">
          <input value={cidr} onChange={(e) => setCidr(e.target.value)} />
          <button className="primary" onClick={async () => setAcl(await api("/api/architect/acl", { method: "POST", body: JSON.stringify({ cidr, proto: "ip", dest: "any", action: "permit" }) }))}>Build</button>
        </div>
        {acl && <pre className="mono-out">{`${acl.ios_extended}\n${acl.nxos}\n${acl.prefix_list}`}</pre>}
      </div>
    </div>
  );
}

function Type7() {
  const [text, setText] = useState("104D000A0618");
  const [mode, setMode] = useState("decode");
  const [out, setOut] = useState("");
  return (
    <div className="card">
      <h3>Cisco type-7</h3>
      <p>The reversible VTY/enable password every CCIE has decoded on a whiteboard. Type-5/8/9 are hashes — this is not those.</p>
      <div className="row">
        <select value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="decode">Decode</option>
          <option value="encode">Encode</option>
        </select>
        <input value={text} onChange={(e) => setText(e.target.value)} style={{ flex: 1 }} />
        <button className="primary" onClick={async () => {
          const r = await api<{ result: string }>("/api/architect/type7", { method: "POST", body: JSON.stringify({ text, mode }) });
          setOut(r.result);
        }}>Run</button>
      </div>
      {out && <pre className="mono-out">{out}</pre>}
    </div>
  );
}

function DiffPad() {
  const [before, setBefore] = useState("hostname OLD\ninterface Gi0/1\n ip address 10.1.1.1 255.255.255.0\n");
  const [after, setAfter] = useState("hostname NEW\ninterface Gi0/1\n ip address 10.1.1.2 255.255.255.0\n no ip redirects\n");
  const [diff, setDiff] = useState<any>(null);
  return (
    <div className="card">
      <h3>Config diff</h3>
      <p>Paste last night’s `show run` and today’s. Same job as `diff` before you hit enter on the live box.</p>
      <div className="grid-2">
        <div className="field"><span>Before</span><textarea rows={12} value={before} onChange={(e) => setBefore(e.target.value)} style={{ fontFamily: "var(--mono)" }} /></div>
        <div className="field"><span>After</span><textarea rows={12} value={after} onChange={(e) => setAfter(e.target.value)} style={{ fontFamily: "var(--mono)" }} /></div>
      </div>
      <button className="primary" onClick={async () => setDiff(await api("/api/architect/diff", { method: "POST", body: JSON.stringify({ before, after }) }))}>Diff</button>
      {diff && <pre className="mono-out">{`+${diff.added} / -${diff.removed}\n\n${diff.diff}`}</pre>}
    </div>
  );
}

function MigratePad() {
  const [line, setLine] = useState("permit tcp any host 10.8.8.10 eq 443");
  const [target, setTarget] = useState("paloalto");
  const [out, setOut] = useState<any>(null);
  return (
    <div className="card">
      <h3>Firewall rule sketch</h3>
      <p>ASA / IOS ACL → PAN, Forti, Check Point. A starting point for a NextHop-style migration, not a full policy converter.</p>
      <div className="row">
        <input value={line} onChange={(e) => setLine(e.target.value)} style={{ flex: 1 }} />
        <select value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="paloalto">Palo Alto</option>
          <option value="fortinet">Fortinet</option>
          <option value="cisco_asa">Cisco ASA</option>
          <option value="checkpoint">Check Point</option>
        </select>
        <button className="primary" onClick={async () => setOut(await api("/api/architect/translate", { method: "POST", body: JSON.stringify({ line, target }) }))}>Translate</button>
      </div>
      {out && <pre className="mono-out">{out.sketch}\n\n# {out.caveat}</pre>}
    </div>
  );
}

function Cookbook() {
  const [book, setBook] = useState<Record<string, { name: string; command: string; why: string }[]>>({});
  useEffect(() => { api("/api/architect/cookbook").then(setBook); }, []);
  return (
    <div className="grid-2">
      {Object.entries(book).map(([track, cmds]) => (
        <div className="card" key={track}>
          <h3>{track}</h3>
          {cmds.map((c) => (
            <div key={c.name} style={{ marginBottom: 10 }}>
              <strong>{c.name}</strong>
              <div style={{ color: "var(--muted)", fontSize: 12 }}>{c.why}</div>
              <pre className="mono-out">{c.command}</pre>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function Runbooks() {
  const [rows, setRows] = useState<{ id: string; title: string; steps: string[] }[]>([]);
  useEffect(() => { api("/api/architect/runbooks").then(setRows); }, []);
  return (
    <div className="grid-2">
      {rows.map((r) => (
        <div className="card" key={r.id}>
          <h3>{r.title}</h3>
          <ol>
            {r.steps.map((s) => <li key={s} style={{ marginBottom: 6 }}>{s}</li>)}
          </ol>
        </div>
      ))}
    </div>
  );
}

function Lookups() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { api("/api/architect/lookups").then(setData); }, []);
  if (!data) return null;
  return (
    <div className="grid-2">
      <div className="card">
        <h3>DSCP / CoS</h3>
        <table className="table">
          <thead><tr><th>Name</th><th>DSCP</th><th>CoS</th><th>Use</th></tr></thead>
          <tbody>{data.dscp.map((d: any) => <tr key={d.name}><td>{d.name}</td><td>{d.dscp}</td><td>{d.cos}</td><td>{d.use}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="card">
        <h3>Ports engineers actually hit</h3>
        <table className="table">
          <thead><tr><th>Port</th><th>Name</th></tr></thead>
          <tbody>{data.ports.map((p: any) => <tr key={p.port}><td>{p.port}</td><td>{p.name}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="card">
        <h3>STP priority</h3>
        <table className="table">
          <thead><tr><th>Priority</th><th>Note</th></tr></thead>
          <tbody>{data.stp.map((s: any) => <tr key={s.priority}><td>{s.priority}</td><td>{s.note}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}
