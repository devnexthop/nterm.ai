import { useEffect, useState } from "react";
import { api } from "../api";
import type { McpServer, Settings } from "../types";
import { THEMES } from "../themes";

export default function SettingsPage({
  settings,
  onSave,
}: {
  settings: Settings | null;
  onSave: (s: Partial<Settings> & { openai_api_key?: string; bench_api_key?: string }) => Promise<void>;
}) {
  const [key, setKey] = useState("");
  const [model, setModel] = useState(settings?.openai_model || "gpt-4.1-mini");
  const [theme, setTheme] = useState(settings?.theme || "nexthop_dark");
  const [font, setFont] = useState(settings?.font_size || 14);
  const [benchUrl, setBenchUrl] = useState(settings?.bench_api_url || "");
  const [benchMode, setBenchMode] = useState(settings?.bench_mode || "merge");
  const [benchKey, setBenchKey] = useState("");
  const [benchMsg, setBenchMsg] = useState("");
  const [mcp, setMcp] = useState<McpServer[]>([]);
  const [mcpForm, setMcpForm] = useState({ name: "", transport: "sse", url: "", command: "" });

  useEffect(() => {
    api<McpServer[]>("/api/mcp").then(setMcp);
  }, []);
  useEffect(() => {
    if (!settings) return;
    setTheme(settings.theme);
    setFont(settings.font_size);
    setModel(settings.openai_model);
    setBenchUrl(settings.bench_api_url || "");
    setBenchMode(settings.bench_mode || "merge");
  }, [settings]);

  return (
    <div className="page">
      <h1>Settings</h1>
      <div className="grid-2">
        <div className="card">
          <h3>AI — no code</h3>
          <p>Paste an OpenAI API key. NTerm stores it encrypted on this machine. {settings?.openai_configured ? "A key is already stored." : "No key stored yet."}</p>
          <div className="field"><span>API key</span><input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-..." /></div>
          <div className="field"><span>Model</span><input value={model} onChange={(e) => setModel(e.target.value)} /></div>
          <button className="primary" onClick={() => onSave({ openai_api_key: key || undefined, openai_model: model })}>Save AI</button>
        </div>
        <div className="card">
          <h3>Theme & terminal</h3>
          <div className="field">
            <span>Theme</span>
            <select value={theme} onChange={(e) => { setTheme(e.target.value); onSave({ theme: e.target.value }); }}>
              <optgroup label="NextHop team">
                {THEMES.filter((t) => t.id.startsWith("nexthop")).map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
              </optgroup>
              <optgroup label="Classic terminals">
                {THEMES.filter((t) => !t.id.startsWith("nexthop")).map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
              </optgroup>
            </select>
          </div>
          <div className="field">
            <span>Font size</span>
            <input type="number" value={font} onChange={(e) => setFont(Number(e.target.value))} />
          </div>
          <button className="ghost" onClick={() => onSave({ font_size: font, theme })}>Save display</button>
        </div>
        <div className="card">
          <h3>Engineer bench feed</h3>
          <p>
            Cookbooks and runbooks come from <code>https://nterm.ai/bench-feed.json</code>.
            Host <code>site/bench-feed.json</code> on that domain. Contract: <code>/api/architect/example-feed</code>.
          </p>
          <div className="field">
            <span>Feed URL</span>
            <input value={benchUrl} onChange={(e) => setBenchUrl(e.target.value)} placeholder="https://nterm.ai/bench-feed.json" />
          </div>
          <div className="field">
            <span>Mode</span>
            <select value={benchMode} onChange={(e) => setBenchMode(e.target.value)}>
              <option value="merge">Merge with built-in</option>
              <option value="remote">Remote only</option>
              <option value="local">Built-in only</option>
            </select>
          </div>
          <div className="field">
            <span>Optional API key {settings?.bench_key_configured ? "(stored)" : ""}</span>
            <input type="password" value={benchKey} onChange={(e) => setBenchKey(e.target.value)} placeholder="Bearer / X-NTerm-Key" />
          </div>
          <div className="row">
            <button className="primary" onClick={() => onSave({ bench_api_url: benchUrl, bench_mode: benchMode, bench_api_key: benchKey || undefined })}>Save feed</button>
            <button className="ghost" onClick={async () => {
              try {
                const r = await api<{ ok: boolean; error?: string; meta?: { source?: string } }>("/api/architect/refresh", { method: "POST" });
                setBenchMsg(r.ok ? `Pulled from ${r.meta?.source || "server"}` : (r.error || "Pull failed — using cache/builtin"));
              } catch (e: any) {
                setBenchMsg(e.message);
              }
            }}>Pull now</button>
          </div>
          {benchMsg && <p style={{ color: "var(--muted)" }}>{benchMsg}</p>}
        </div>
        <div className="card">
          <h3>MCP servers</h3>
          <p>Point NTerm at another MCP server so the AI can pull CMDB, NetBox, tickets, or your own tools.</p>
          {mcp.map((m) => (
            <div className="row" key={m.id}>
              <strong>{m.name}</strong>
              <span>{m.transport} {m.url || m.command}</span>
              <button className="ghost" onClick={() => api(`/api/mcp/${m.id}`, { method: "DELETE" }).then(() => setMcp(mcp.filter((x) => x.id !== m.id)))}>Remove</button>
            </div>
          ))}
          <div className="field"><span>Name</span><input value={mcpForm.name} onChange={(e) => setMcpForm({ ...mcpForm, name: e.target.value })} /></div>
          <div className="field"><span>URL (SSE/HTTP)</span><input value={mcpForm.url} onChange={(e) => setMcpForm({ ...mcpForm, url: e.target.value })} /></div>
          <div className="field"><span>or stdio command</span><input value={mcpForm.command} onChange={(e) => setMcpForm({ ...mcpForm, command: e.target.value })} /></div>
          <button className="primary" onClick={async () => {
            const created = await api<McpServer>("/api/mcp", { method: "POST", body: JSON.stringify({ ...mcpForm, enabled: true, args: "", notes: "" }) });
            setMcp([...mcp, created]);
            setMcpForm({ name: "", transport: "sse", url: "", command: "" });
          }}>Add MCP</button>
        </div>
        <div className="card">
          <h3>About NTerm</h3>
          <p>
            A NextHop LLC product — nterm.ai · nexthopllc.com. Sessions, broadcast, syslog, TFTP, DHCP, analyzers, and a CCIE bench.
          </p>
          <div className="row">
            <img src="/icon.png" alt="NTerm" style={{ width: 48, height: 48, borderRadius: 10 }} />
            <div>
              <strong>NTerm</strong>
              <div style={{ color: "var(--muted)" }}>nterm.ai · v0.1.0</div>
            </div>
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <a className="primary" href="https://nterm.ai" target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>nterm.ai</a>
            <a className="ghost" href="https://nterm.ai/download" target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>Downloads</a>
          </div>
        </div>
      </div>
    </div>
  );
}
