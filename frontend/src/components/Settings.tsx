import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { AiModelOption, AiModelsResponse, McpServer, Settings } from "../types";
import { THEMES } from "../themes";

const CUSTOM = "__custom__";

function recognizeKey(raw: string, currentBase: string): { provider?: string; baseUrl?: string } {
  const k = raw.trim();
  if (k.startsWith("sk-ant-")) return { provider: "anthropic" };
  if (k.startsWith("sk-or-")) return { provider: "compatible", baseUrl: currentBase || "https://openrouter.ai/api/v1" };
  if (k.startsWith("gsk_")) return { provider: "compatible", baseUrl: currentBase || "https://api.groq.com/openai/v1" };
  return {};
}

export default function SettingsPage({
  settings,
  onSave,
}: {
  settings: Settings | null;
  onSave: (s: Partial<Settings> & {
    openai_api_key?: string;
    anthropic_api_key?: string;
    bench_api_key?: string;
  }) => Promise<void>;
}) {
  const [provider, setProvider] = useState(settings?.ai_provider || "openai");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(settings?.openai_model || "gpt-4.1-mini");
  const [customModel, setCustomModel] = useState("");
  const [useCustom, setUseCustom] = useState(false);
  const [baseUrl, setBaseUrl] = useState(settings?.ai_base_url || "");
  const [cacheOn, setCacheOn] = useState(settings?.ai_cache_enabled ?? true);
  const [theme, setTheme] = useState(settings?.theme || "nexthop_dark");
  const [font, setFont] = useState(settings?.font_size || 14);
  const [benchUrl, setBenchUrl] = useState(settings?.bench_api_url || "");
  const [benchMode, setBenchMode] = useState(settings?.bench_mode || "merge");
  const [benchKey, setBenchKey] = useState("");
  const [benchMsg, setBenchMsg] = useState("");
  const [mcp, setMcp] = useState<McpServer[]>([]);
  const [mcpForm, setMcpForm] = useState({ name: "", transport: "sse", url: "", command: "" });
  const [saved, setSaved] = useState("");
  const [liveModels, setLiveModels] = useState<AiModelOption[]>([]);
  const [modelsBusy, setModelsBusy] = useState(false);
  const [modelsErr, setModelsErr] = useState("");
  const [modelFilter, setModelFilter] = useState("");

  const hasStoredKey = provider === "anthropic" ? !!settings?.anthropic_configured : !!settings?.openai_configured;
  const options = useMemo(() => {
    const rows = [...liveModels];
    if (model && !rows.some((m) => m.id === model)) {
      rows.unshift({ id: model, label: `${model} (saved)` });
    }
    const q = modelFilter.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((m) => m.id.toLowerCase().includes(q) || m.label.toLowerCase().includes(q));
  }, [liveModels, model, modelFilter]);

  useEffect(() => {
    api<McpServer[]>("/api/mcp").then(setMcp);
  }, []);
  useEffect(() => {
    if (!settings) return;
    setTheme(settings.theme);
    setFont(settings.font_size);
    setModel(settings.openai_model);
    setProvider(settings.ai_provider || "openai");
    setBaseUrl(settings.ai_base_url || "");
    setCacheOn(settings.ai_cache_enabled ?? true);
    setBenchUrl(settings.bench_api_url || "");
    setBenchMode(settings.bench_mode || "merge");
    setUseCustom(false);
  }, [settings]);

  useEffect(() => {
    let cancelled = false;
    const pasted = apiKey.trim();
    const ollama = provider === "compatible" && /^https?:\/\//.test(baseUrl.trim());
    if (!pasted && !hasStoredKey && !ollama) return;
    if (pasted && pasted.length < 16 && !ollama) return;

    const timer = window.setTimeout(async () => {
      setModelsBusy(true);
      setModelsErr("");
      try {
        const r = await api<AiModelsResponse>("/api/ai/models", {
          method: "POST",
          body: JSON.stringify({
            api_key: pasted || undefined,
            provider,
            base_url: provider === "compatible" ? baseUrl.trim() : "",
          }),
        });
        if (cancelled) return;
        if (r.provider && r.provider !== provider) setProvider(r.provider);
        if (r.base_url && provider === "compatible" && r.base_url !== baseUrl) setBaseUrl(r.base_url);
        setLiveModels(r.models || []);
        setModelsErr(r.error || "");
      } catch (e: unknown) {
        if (!cancelled) {
          setLiveModels([]);
          setModelsErr(e instanceof Error ? e.message : "Could not list models");
        }
      } finally {
        if (!cancelled) setModelsBusy(false);
      }
    }, pasted ? 500 : 80);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [apiKey, provider, baseUrl, hasStoredKey]);

  function onKeyChange(raw: string) {
    setApiKey(raw);
    const rec = recognizeKey(raw, baseUrl);
    if (rec.provider) setProvider(rec.provider);
    if (rec.baseUrl) setBaseUrl(rec.baseUrl);
  }

  async function saveAi() {
    const resolved = useCustom ? (customModel.trim() || model) : model;
    await onSave({
      ai_provider: provider,
      openai_model: resolved,
      ai_base_url: provider === "compatible" ? baseUrl : "",
      ai_cache_enabled: cacheOn,
      openai_api_key: provider !== "anthropic" ? (apiKey || undefined) : undefined,
      anthropic_api_key: provider === "anthropic" ? (apiKey || undefined) : undefined,
    });
    setApiKey("");
    setSaved("Saved on this machine.");
  }

  const keyHint = provider === "anthropic"
    ? (settings?.anthropic_configured ? "An Anthropic key is stored. Paste a new one to replace it." : "No Anthropic key yet.")
    : (settings?.openai_configured ? "A key is stored. Paste a new one to replace it." : "No key stored yet.");

  return (
    <div className="page">
      <h1>Settings</h1>
      <div className="grid-2">
        <div className="card">
          <h3>AI — your key, your model</h3>
          <p>
            Paste an API key. NTerm recognizes the provider, pulls the models that key can use, and you pick one.
            Not a ChatGPT / Claude subscription. Keys stay encrypted on this machine. {keyHint}
          </p>
          <div className="field">
            <span>API key</span>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => onKeyChange(e.target.value)}
              placeholder="sk-… / sk-ant-… / gsk_…"
              autoComplete="off"
            />
          </div>
          <div className="field">
            <span>Provider</span>
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="compatible">Compatible (OpenRouter, Groq, Azure, Ollama…)</option>
            </select>
          </div>
          {provider === "compatible" && (
            <div className="field"><span>Base URL</span>
              <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.groq.com/openai/v1" />
            </div>
          )}
          {liveModels.length > 20 && (
            <div className="field">
              <span>Filter models</span>
              <input value={modelFilter} onChange={(e) => setModelFilter(e.target.value)} placeholder="gpt-4.1, claude, llama…" />
            </div>
          )}
          <div className="field">
            <span>Model</span>
            <select
              value={useCustom ? CUSTOM : model}
              onChange={(e) => {
                if (e.target.value === CUSTOM) {
                  setUseCustom(true);
                  setCustomModel(liveModels.some((m) => m.id === model) ? "" : model);
                } else {
                  setUseCustom(false);
                  setModel(e.target.value);
                }
              }}
            >
              {options.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
              <option value={CUSTOM}>Custom — type the model id</option>
            </select>
          </div>
          {modelsBusy && <p className="model-status">Asking the provider for models this key can use…</p>}
          {!modelsBusy && liveModels.length > 0 && (
            <p className="model-status">{liveModels.length} models available for this key.</p>
          )}
          {modelsErr && <p className="model-status err">{modelsErr} You can still type a model id.</p>}
          {useCustom && (
            <div className="field"><span>Custom model id</span>
              <input
                value={customModel}
                onChange={(e) => { setCustomModel(e.target.value); setModel(e.target.value); }}
                placeholder={provider === "anthropic" ? "claude-sonnet-4-6" : "gpt-4.1-mini"}
              />
            </div>
          )}
          <label className="row">
            <input type="checkbox" checked={cacheOn} onChange={(e) => setCacheOn(e.target.checked)} />
            Cache identical Do-bar asks locally (0 tokens on hit)
          </label>
          <p className="hint">NTerm MCP for other agents: <code>http://127.0.0.1:8787/mcp</code></p>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="primary" onClick={saveAi}>Save AI</button>
            {saved && <span style={{ color: "var(--ok)" }}>{saved}</span>}
          </div>
        </div>
        <div className="card">
          <h3>Theme & terminal</h3>
          <div className="field">
            <span>Theme</span>
            <select value={theme} onChange={(e) => { setTheme(e.target.value); onSave({ theme: e.target.value }); }}>
              <optgroup label="ValeronLabs team">
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
              } catch (e: unknown) {
                setBenchMsg(e instanceof Error ? e.message : String(e));
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
            A ValeronLabs LLC product — nterm.ai. Sessions, broadcast, syslog, TFTP, DHCP, analyzers, and a CCIE bench.
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
