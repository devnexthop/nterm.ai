import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { AiModelOption, AiModelsResponse, Credential, McpServer, Settings } from "../types";
import { THEMES } from "../themes";

const CUSTOM = "__custom__";

/* Web faces are loaded in index.html; the last three are system faces that
   exist on macOS or Windows and cost nothing to offer. */
const MONO_FACES = [
  "IBM Plex Mono",
  "JetBrains Mono",
  "Fira Code",
  "Source Code Pro",
  "Menlo",
  "Consolas",
  "Courier New",
];

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
    relay_token?: string;
  }) => Promise<void>;
}) {
  const [provider, setProvider] = useState(settings?.ai_provider || "openai");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(settings?.openai_model || "gpt-4.1-mini");
  const [customModel, setCustomModel] = useState("");
  const [useCustom, setUseCustom] = useState(false);
  const [baseUrl, setBaseUrl] = useState(settings?.ai_base_url || "");
  const [cacheOn, setCacheOn] = useState(settings?.ai_cache_enabled ?? true);
  const [theme, setTheme] = useState(settings?.theme || "valeron");
  const [font, setFont] = useState(settings?.font_size || 14);
  const [fontFam, setFontFam] = useState(settings?.font_family || "IBM Plex Mono");
  const [benchUrl, setBenchUrl] = useState(settings?.bench_api_url || "");
  const [benchMode, setBenchMode] = useState(settings?.bench_mode || "merge");
  const [benchKey, setBenchKey] = useState("");
  const [benchMsg, setBenchMsg] = useState("");
  const [relayToken, setRelayToken] = useState("");
  const [mcp, setMcp] = useState<McpServer[]>([]);
  const [creds, setCreds] = useState<Credential[]>([]);
  const [imp, setImp] = useState<{
    filename: string; content: string; format: string;
    rows: any[]; busy: boolean; err: string; done: string; customer: string;
  }>({ filename: "", content: "", format: "auto", rows: [], busy: false, err: "", done: "", customer: "" });
  const [credForm, setCredForm] = useState<{
    id?: number; name: string; username: string; password: string;
    enable_password: string; device_type: string; notes: string;
  } | null>(null);
  const [mcpForm, setMcpForm] = useState({ name: "", transport: "sse", url: "", command: "" });
  const [saved, setSaved] = useState("");
  const [liveModels, setLiveModels] = useState<AiModelOption[]>([]);
  const [modelsBusy, setModelsBusy] = useState(false);
  const [modelsErr, setModelsErr] = useState("");
  const [modelFilter, setModelFilter] = useState("");
  const [detected, setDetected] = useState("");
  const [tab, setTab] = useState<"ai" | "appearance" | "logging" | "bench" | "mcp" | "sharing" | "vault" | "credentials" | "import" | "about">("ai");

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
    loadCreds();
  }, []);

  function loadCreds() {
    api<Credential[]>("/api/credentials").then(setCreds).catch(() => {});
  }

  async function saveCred() {
    if (!credForm?.name.trim()) return;
    const body = {
      name: credForm.name,
      username: credForm.username,
      device_type: credForm.device_type,
      notes: credForm.notes,
      // Empty means "leave the stored one alone" — the API never returns a
      // password, so a blank field must not be able to erase one.
      password: credForm.password || undefined,
      enable_password: credForm.enable_password || undefined,
    };
    if (credForm.id) {
      await api(`/api/credentials/${credForm.id}`, { method: "PUT", body: JSON.stringify(body) });
    } else {
      await api("/api/credentials", { method: "POST", body: JSON.stringify(body) });
    }
    setCredForm(null);
    loadCreds();
  }
  useEffect(() => {
    if (!settings) return;
    setTheme(settings.theme);
    setFont(settings.font_size);
    setFontFam(settings.font_family || "IBM Plex Mono");
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
    if (rec.provider) {
      setProvider(rec.provider);
      /* Recognising the provider from the prefix is the one genuinely clever
         thing this screen does. Flag it so the row can say so, briefly. */
      setDetected(rec.provider);
      window.setTimeout(() => setDetected(""), 2200);
    }
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

  const SECTIONS = [
    { id: "ai" as const, label: "AI", led: hasStoredKey ? "var(--ok)" : "var(--muted)" },
    { id: "appearance" as const, label: "Appearance", led: "" },
    { id: "logging" as const, label: "Logging", led: settings?.log_sessions ? "var(--ok)" : "var(--muted)" },
    { id: "bench" as const, label: "Bench", led: benchUrl ? "var(--ok)" : "var(--muted)" },
    { id: "mcp" as const, label: "MCP", led: mcp.length ? "var(--ok)" : "var(--muted)" },
    { id: "sharing" as const, label: "Sharing", led: settings?.relay_configured ? "var(--ok)" : "var(--pending)" },
    { id: "vault" as const, label: "Vault", led: "" },
    { id: "credentials" as const, label: "Credentials", led: creds.length ? "var(--ok)" : "var(--muted)" },
    { id: "import" as const, label: "Import", led: "" },
    { id: "about" as const, label: "About", led: "" },
  ];

  return (
    <div className="set-wrap">
      <nav className="set-rail" aria-label="Settings sections">
        <div className="cap">Settings</div>
        {SECTIONS.map((sec) => (
          <button
            key={sec.id}
            className={`set-item ${tab === sec.id ? "on" : ""}`}
            onClick={() => setTab(sec.id)}
            aria-current={tab === sec.id ? "true" : undefined}
          >
            {sec.label}
            {sec.led && <span className="led" style={{ background: sec.led }} />}
          </button>
        ))}
      </nav>

      <div className="set-body">
        {tab === "ai" && (
          <>
            <div className="set-cap">
              <h1>AI</h1>
              <span className="n">Your key, your model — not a subscription</span>
            </div>
            <p style={{ color: "var(--muted)", margin: 0, maxWidth: "66ch" }}>
              Paste an API key. NTerm recognizes the provider, pulls the models that key can use, and you pick one.
              Keys stay encrypted on this machine. {keyHint}
            </p>
            <div className="sched">
              <div className="fr"><span className="k">API key</span><span className={`v keyrow ${modelsBusy ? "scanning" : ""}`}>
                <input type="password" value={apiKey} onChange={(e) => onKeyChange(e.target.value)}
                  placeholder="sk-… / sk-ant-… / gsk_…" autoComplete="off" />
                {modelsBusy
                  ? <span className="stat scan-note">reading key…</span>
                  : hasStoredKey && <span className="stat ok pop">● stored</span>}
              </span></div>
              <div className="fr"><span className="k">Provider</span><span className="v">
                <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="compatible">Compatible (OpenRouter, Groq, Azure, Ollama…)</option>
                </select>
                {detected
                  ? <span className="stat ok pop">✓ {detected} detected</span>
                  : <span className="stat">detected from key prefix</span>}
              </span></div>
              {provider === "compatible" && (
                <div className="fr"><span className="k">Base URL</span><span className="v">
                  <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.groq.com/openai/v1" />
                </span></div>
              )}
              {liveModels.length > 20 && (
                <div className="fr"><span className="k">Filter models</span><span className="v">
                  <input value={modelFilter} onChange={(e) => setModelFilter(e.target.value)} placeholder="gpt-4.1, claude, llama…" />
                </span></div>
              )}
              <div className="fr"><span className="k">Model</span><span className="v">
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
                {modelsBusy && <span className="stat"><span className="dots"><i /><i /><i /></span> asking the provider…</span>}
                {!modelsBusy && liveModels.length > 0 && <span className="stat ok pop">{liveModels.length} available</span>}
              </span></div>
              {useCustom && (
                <div className="fr"><span className="k">Custom model id</span><span className="v">
                  <input value={customModel} onChange={(e) => { setCustomModel(e.target.value); setModel(e.target.value); }}
                    placeholder={provider === "anthropic" ? "claude-sonnet-4-6" : "gpt-4.1-mini"} />
                </span></div>
              )}
              <div className="fr"><span className="k">Cache asks</span><span className="v">
                <label className="row" style={{ gap: 9 }}>
                  <input type="checkbox" checked={cacheOn} onChange={(e) => setCacheOn(e.target.checked)} style={{ flex: "0 0 auto", minWidth: 0 }} />
                  <span style={{ fontSize: 12.5, color: "var(--muted)" }}>Identical Do-bar asks cost 0 tokens on a hit</span>
                </label>
              </span></div>
              <div className="fr"><span className="k">Serve MCP</span><span className="v">
                <input readOnly value="http://127.0.0.1:8787/mcp" />
                <button className="ghost" onClick={() => navigator.clipboard?.writeText("http://127.0.0.1:8787/mcp")}>Copy</button>
              </span></div>
            </div>
            {modelsErr && <p className="model-status err">{modelsErr} You can still type a model id.</p>}
            <div className="row">
              <button className="primary" onClick={saveAi}>Save AI</button>
              {saved && <span style={{ color: "var(--ok)", fontSize: 12.5 }}>{saved}</span>}
            </div>
          </>
        )}

        {tab === "appearance" && (
          <>
            <div className="set-cap">
              <h1>Appearance</h1>
              <span className="n">Changes apply straight away</span>
            </div>
            <p className="set-lbl">Terminal theme</p>
            {/* A dropdown made you apply a theme to see it. Tiles let you look
                before you choose — each renders real values from themes.ts. */}
            <div className="theme-grid">
              {THEMES.map((t) => (
                <button
                  key={t.id}
                  className={`theme-tile ${theme === t.id ? "on" : ""}`}
                  onClick={() => { setTheme(t.id); onSave({ theme: t.id }); }}
                  aria-pressed={theme === t.id}
                  title={t.label}
                >
                  <span className="tt-prev" style={{ background: t.term.background, color: t.term.foreground }}>
                    <span style={{ color: t.term.cursor }}>sw01#</span> sh ip int br<br />
                    Gi0/0 <span style={{ color: t.term.green }}>up</span> <span style={{ color: t.term.green }}>up</span><br />
                    Gi0/1 <span style={{ color: t.term.green }}>up</span> <span style={{ color: t.term.red }}>down</span>
                  </span>
                  <span className="tt-meta">
                    <span className="tt-name">{t.label.replace(" (team)", "")}</span>
                    <span className="tt-strip">
                      <i style={{ background: t.term.background }} />
                      <i style={{ background: t.term.cursor }} />
                      <i style={{ background: t.term.green }} />
                      <i style={{ background: t.term.red }} />
                    </span>
                  </span>
                </button>
              ))}
            </div>
            <p className="set-lbl">Terminal type</p>
            <div className="sched">
              <div className="fr"><span className="k">Typeface</span><span className="v">
                <select value={fontFam} onChange={(e) => { setFontFam(e.target.value); onSave({ font_family: e.target.value }); }}>
                  {MONO_FACES.map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
                <span className="stat">applies to every terminal pane</span>
              </span></div>
              <div className="fr"><span className="k">Font size</span><span className="v">
                <input type="range" min={10} max={22} value={font}
                  onChange={(e) => { const n = Number(e.target.value); setFont(n); onSave({ font_size: n }); }}
                  style={{ flex: 1, minWidth: 150, padding: 0, background: "none" }} />
                <span className="stat">{font} px</span>
              </span></div>
              <div className="fr"><span className="k">Preview</span><span className="v">
                <span style={{ fontFamily: `"${fontFam}", ui-monospace, monospace`, fontSize: font, color: "var(--text)" }}>
                  Gi0/1  10.14.9.1  YES NVRAM  up  down
                </span>
              </span></div>
            </div>
          </>
        )}

        {tab === "logging" && (
          <>
            <div className="set-cap"><h1>Logging</h1><span className="n">./data/logs</span></div>
            <p style={{ color: "var(--muted)", margin: 0, maxWidth: "66ch" }}>
              Every session can be written to disk as it happens — the thing you want during an
              incident and forget to switch on beforehand. A log is a transcript of everything the
              device printed, <strong>including any secret you typed</strong>, so it lives in the same
              vault as your credentials and is never sent anywhere.
            </p>
            <div className="sched">
              <div className="fr"><span className="k">Record sessions</span><span className="v">
                <label className="row" style={{ gap: 9 }}>
                  <input type="checkbox" checked={!!settings?.log_sessions}
                    onChange={(e) => onSave({ log_sessions: e.target.checked })} />
                  <span style={{ fontSize: 12.5, color: "var(--muted)" }}>
                    Write a log per session to <code>./data/logs/session-&lt;id&gt;/</code>
                  </span>
                </label>
              </span></div>
              <div className="fr"><span className="k">Redact on export</span><span className="v">
                <label className="row" style={{ gap: 9 }}>
                  <input type="checkbox" checked={!!settings?.log_redact}
                    onChange={(e) => onSave({ log_redact: e.target.checked })} />
                  <span style={{ fontSize: 12.5, color: "var(--muted)" }}>
                    Strip key blocks, type-7 strings and community strings when a log leaves the vault
                  </span>
                </label>
              </span></div>
              <div className="fr"><span className="k">Location</span><span className="v">
                <input readOnly value="./data/logs" className="mono" />
                <span className="stat">bind-mounted to /data in Docker</span>
              </span></div>
            </div>
          </>
        )}

        {tab === "bench" && (
          <>
            <div className="set-cap"><h1>Bench</h1><span className="n">Cookbooks and runbooks</span></div>
            <p style={{ color: "var(--muted)", margin: 0, maxWidth: "66ch" }}>
              Feed comes from <code>https://nterm.ai/bench-feed.json</code>. If it is unreachable NTerm keeps the
              last cache, then falls back to built-in.
            </p>
            <div className="sched">
              <div className="fr"><span className="k">Feed URL</span><span className="v">
                <input value={benchUrl} onChange={(e) => setBenchUrl(e.target.value)} placeholder="https://nterm.ai/bench-feed.json" />
              </span></div>
              <div className="fr"><span className="k">Mode</span><span className="v">
                <select value={benchMode} onChange={(e) => setBenchMode(e.target.value)}>
                  <option value="merge">Merge with built-in</option>
                  <option value="remote">Remote only</option>
                  <option value="local">Built-in only</option>
                </select>
              </span></div>
              <div className="fr"><span className="k">API key</span><span className="v">
                <input type="password" value={benchKey} onChange={(e) => setBenchKey(e.target.value)} placeholder="Bearer / X-NTerm-Key" />
                {settings?.bench_key_configured && <span className="stat ok">● stored</span>}
              </span></div>
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
              {benchMsg && <span className="stat">{benchMsg}</span>}
            </div>
          </>
        )}

        {tab === "mcp" && (
          <>
            <div className="set-cap"><h1>MCP servers</h1><span className="n">{mcp.length} configured</span></div>
            <p style={{ color: "var(--muted)", margin: 0, maxWidth: "66ch" }}>
              Point NTerm at another MCP server so the AI can pull CMDB, NetBox, tickets, or your own tools.
            </p>
            {mcp.length > 0 && (
              <div className="vault">
                {mcp.map((m) => (
                  <div className="vrow" key={m.id}>
                    <div><div className="nm">{m.name}</div><div className="sub">{m.transport} · {m.url || m.command}</div></div>
                    <span className="pill set">Enabled</span>
                    <button className="ghost" onClick={() => api(`/api/mcp/${m.id}`, { method: "DELETE" }).then(() => setMcp(mcp.filter((x) => x.id !== m.id)))}>Remove</button>
                  </div>
                ))}
              </div>
            )}
            <div className="sched">
              <div className="fr"><span className="k">Name</span><span className="v"><input value={mcpForm.name} onChange={(e) => setMcpForm({ ...mcpForm, name: e.target.value })} /></span></div>
              <div className="fr"><span className="k">URL (SSE/HTTP)</span><span className="v"><input value={mcpForm.url} onChange={(e) => setMcpForm({ ...mcpForm, url: e.target.value })} /></span></div>
              <div className="fr"><span className="k">or stdio command</span><span className="v"><input value={mcpForm.command} onChange={(e) => setMcpForm({ ...mcpForm, command: e.target.value })} /></span></div>
            </div>
            <div className="row">
              <button className="primary" onClick={async () => {
                const created = await api<McpServer>("/api/mcp", { method: "POST", body: JSON.stringify({ ...mcpForm, enabled: true, args: "", notes: "" }) });
                setMcp([...mcp, created]);
                setMcpForm({ name: "", transport: "sse", url: "", command: "" });
              }}>Add MCP</button>
            </div>
          </>
        )}

        {tab === "sharing" && (
          <>
            <div className="set-cap"><h1>Session sharing</h1><span className="n">Read-only, via relay</span></div>
            <p style={{ color: "var(--muted)", margin: 0, maxWidth: "66ch" }}>
              Share a live session read-only at sessions.nterm.ai. Viewers watch; input is never accepted from the
              browser. Known secret patterns are redacted on the relay before anyone sees them — but that is pattern
              matching, not a guarantee, so treat a shared session as visible.
              {settings?.relay_configured ? " A relay token is stored." : " No relay token yet — Share stays disabled until one is saved."}
            </p>
            <div className="sched">
              <div className="fr"><span className="k">Relay token</span><span className="v">
                <input type="password" value={relayToken} onChange={(e) => setRelayToken(e.target.value)}
                  placeholder={settings?.relay_configured ? "stored — paste a new one to replace" : "paste the relay token"} />
              </span></div>
            </div>
            <div className="row">
              <button className="primary" onClick={() => onSave({ relay_token: relayToken })} disabled={!relayToken.trim()}>Save relay token</button>
              <a className="ghost" href="https://sessions.nterm.ai/" target="_blank" rel="noopener"
                 style={{ textDecoration: "none", display: "inline-flex", alignItems: "center" }}>Open relay</a>
            </div>
          </>
        )}

        {tab === "vault" && (
          <>
            <div className="set-cap"><h1>Vault</h1><span className="n">./data — treat like a password database</span></div>
            <p style={{ color: "var(--muted)", margin: 0, maxWidth: "66ch" }}>
              What this machine holds. Nothing here is ever displayed after saving — the vault reports state, not
              contents. Deleting <code>./data</code> wipes it and is not recoverable.
            </p>
            <div className="vault">
              {[
                { nm: "Anthropic API key", sub: "AI · encrypted at rest", on: !!settings?.anthropic_configured },
                { nm: "OpenAI / compatible key", sub: "AI · encrypted at rest", on: !!settings?.openai_configured },
                { nm: "Bench feed key", sub: "Bench · Bearer / X-NTerm-Key", on: !!settings?.bench_key_configured },
                { nm: "Relay token", sub: "Sharing · Share is disabled without it", on: !!settings?.relay_configured },
                { nm: "Device credentials", sub: `Credentials · ${creds.length} stored`, on: creds.length > 0 },
              ].map((r) => (
                <div className="vrow" key={r.nm}>
                  <div><div className="nm">{r.nm}</div><div className="sub">{r.sub}</div></div>
                  <span className={`pill ${r.on ? "set" : "no"}`}>{r.on ? "Stored" : "Not set"}</span>
                  <button className="ghost" onClick={() => setTab(
                    r.sub.startsWith("AI") ? "ai"
                    : r.sub.startsWith("Bench") ? "bench"
                    : r.sub.startsWith("Credentials") ? "credentials"
                    : "sharing"
                  )}>
                    {r.on ? "Replace" : "Add"}
                  </button>
                </div>
              ))}
            </div>
          </>
        )}

        {tab === "credentials" && (
          <>
            <div className="set-cap">
              <h1>Credentials</h1>
              <span className="n">{creds.length} stored · reusable across sessions</span>
            </div>
            <p style={{ color: "var(--muted)", margin: 0, maxWidth: "66ch" }}>
              A credential is a username and password you reuse across many devices, so a password
              change is one edit instead of two hundred. Passwords are encrypted into the vault and
              <strong> never returned by the API</strong> — this screen can tell you one is stored, not what it is.
            </p>

            {creds.length > 0 && (
              <div className="vault">
                {creds.map((c) => (
                  <div className="vrow" key={c.id}>
                    <div>
                      <div className="nm">{c.name}</div>
                      <div className="sub">
                        {c.username || "no username"}
                        {c.device_type ? ` · ${c.device_type}` : ""}
                        {c.notes ? ` · ${c.notes}` : ""}
                      </div>
                    </div>
                    <span className={`pill ${c.has_password ? "set" : "no"}`}>
                      {c.has_password ? (c.has_enable_password ? "Password + enable" : "Password") : "No password"}
                    </span>
                    <span className="row" style={{ gap: 6 }}>
                      <button className="ghost" onClick={() => setCredForm({
                        id: c.id, name: c.name, username: c.username, password: "",
                        enable_password: "", device_type: c.device_type, notes: c.notes,
                      })}>Edit</button>
                      <button className="danger" onClick={async () => {
                        if (!window.confirm(`Delete credential "${c.name}"? Sessions using it keep their own copy.`)) return;
                        await api(`/api/credentials/${c.id}`, { method: "DELETE" });
                        loadCreds();
                      }}>Delete</button>
                    </span>
                  </div>
                ))}
              </div>
            )}

            {credForm ? (
              <>
                <p className="set-lbl">{credForm.id ? "Edit credential" : "New credential"}</p>
                <div className="sched">
                  <div className="fr"><span className="k">Name</span><span className="v">
                    <input value={credForm.name} placeholder="Core switches — read-only"
                      onChange={(e) => setCredForm({ ...credForm, name: e.target.value })} />
                  </span></div>
                  <div className="fr"><span className="k">Username</span><span className="v">
                    <input value={credForm.username} autoComplete="off"
                      onChange={(e) => setCredForm({ ...credForm, username: e.target.value })} />
                  </span></div>
                  <div className="fr"><span className="k">Password</span><span className="v">
                    <input type="password" value={credForm.password} autoComplete="new-password"
                      placeholder={credForm.id ? "leave blank to keep the stored one" : ""}
                      onChange={(e) => setCredForm({ ...credForm, password: e.target.value })} />
                  </span></div>
                  <div className="fr"><span className="k">Enable password</span><span className="v">
                    <input type="password" value={credForm.enable_password} autoComplete="new-password"
                      placeholder={credForm.id ? "leave blank to keep the stored one" : "Cisco enable / secret"}
                      onChange={(e) => setCredForm({ ...credForm, enable_password: e.target.value })} />
                  </span></div>
                  <div className="fr"><span className="k">Vendor</span><span className="v">
                    <select value={credForm.device_type}
                      onChange={(e) => setCredForm({ ...credForm, device_type: e.target.value })}>
                      <option value="">Any</option>
                      <option value="cisco_ios">Cisco IOS</option>
                      <option value="cisco_nxos">Cisco NX-OS</option>
                      <option value="paloalto">Palo Alto</option>
                      <option value="fortinet">Fortinet</option>
                      <option value="juniper">Juniper</option>
                      <option value="linux">Linux</option>
                    </select>
                  </span></div>
                  <div className="fr"><span className="k">Notes</span><span className="v">
                    <input value={credForm.notes}
                      onChange={(e) => setCredForm({ ...credForm, notes: e.target.value })} />
                  </span></div>
                </div>
                <div className="row">
                  <button className="primary" onClick={saveCred}>{credForm.id ? "Save changes" : "Add credential"}</button>
                  <button className="ghost" onClick={() => setCredForm(null)}>Cancel</button>
                </div>
              </>
            ) : (
              <div className="row">
                <button className="primary" onClick={() => setCredForm({
                  name: "", username: "", password: "", enable_password: "", device_type: "", notes: "",
                })}>Add credential</button>
              </div>
            )}
          </>
        )}

        {tab === "import" && (
          <>
            <div className="set-cap">
              <h1>Import sessions</h1>
              <span className="n">SecureCRT · PuTTY · ssh_config · CSV</span>
            </div>
            <p style={{ color: "var(--muted)", margin: 0, maxWidth: "66ch" }}>
              Bring your existing sessions across instead of retyping them. NTerm reads the
              structure — hosts, ports, usernames, folders — and <strong>never reads stored
              passwords</strong> from another tool's file. You will re-enter those once, as
              credentials.
            </p>

            <div className="sched">
              <div className="fr"><span className="k">File</span><span className="v">
                <input type="file" accept=".ini,.reg,.csv,.tsv,.txt,.conf,config"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    const content = await f.text();
                    setImp((v) => ({ ...v, filename: f.name, content, rows: [], err: "", done: "" }));
                  }} />
              </span></div>
              <div className="fr"><span className="k">Format</span><span className="v">
                <select value={imp.format} onChange={(e) => setImp((v) => ({ ...v, format: e.target.value }))}>
                  <option value="auto">Detect automatically</option>
                  <option value="securecrt">SecureCRT</option>
                  <option value="putty">PuTTY (.reg export)</option>
                  <option value="openssh">OpenSSH config</option>
                  <option value="csv">CSV / TSV</option>
                </select>
                <span className="stat">{imp.filename || "no file chosen"}</span>
              </span></div>
              <div className="fr"><span className="k">Customer</span><span className="v">
                <input value={imp.customer} placeholder="leave blank to use the folder names in the file"
                  onChange={(e) => setImp((v) => ({ ...v, customer: e.target.value }))} />
              </span></div>
            </div>

            <div className="row">
              <button className="primary" disabled={!imp.content || imp.busy}
                onClick={async () => {
                  setImp((v) => ({ ...v, busy: true, err: "", done: "" }));
                  try {
                    const r = await api<{ format: string; count: number; sessions: any[] }>(
                      "/api/import/preview",
                      { method: "POST", body: JSON.stringify({ content: imp.content, format: imp.format, filename: imp.filename }) },
                    );
                    setImp((v) => ({ ...v, busy: false, rows: r.sessions, format: r.format }));
                  } catch (e: any) {
                    setImp((v) => ({ ...v, busy: false, err: e.message || String(e) }));
                  }
                }}>{imp.busy ? "Reading…" : "Preview"}</button>
              {imp.rows.length > 0 && (
                <button className="primary" disabled={imp.busy}
                  onClick={async () => {
                    setImp((v) => ({ ...v, busy: true, err: "", done: "" }));
                    try {
                      const r = await api<{ created: number; skipped: number }>(
                        "/api/import/commit",
                        { method: "POST", body: JSON.stringify({ sessions: imp.rows, customer_name: imp.customer }) },
                      );
                      setImp((v) => ({
                        ...v, busy: false, rows: [], content: "", filename: "",
                        done: `Imported ${r.created} session${r.created === 1 ? "" : "s"}` +
                              (r.skipped ? ` · ${r.skipped} already existed` : ""),
                      }));
                    } catch (e: any) {
                      setImp((v) => ({ ...v, busy: false, err: e.message || String(e) }));
                    }
                  }}>Import {imp.rows.length}</button>
              )}
              {imp.err && <span className="stat" style={{ color: "var(--danger)" }}>{imp.err}</span>}
              {imp.done && <span className="stat ok">{imp.done}</span>}
            </div>

            {imp.rows.length > 0 && (
              <>
                <p className="set-lbl">Preview — {imp.rows.length} session{imp.rows.length === 1 ? "" : "s"} · detected as {imp.format}</p>
                <div className="vault" style={{ maxHeight: 340, overflowY: "auto" }}>
                  {imp.rows.slice(0, 200).map((r, i) => (
                    <div className="vrow" key={i}>
                      <div>
                        <div className="nm">{r.name}</div>
                        <div className="sub">
                          {r.kind} · {r.host}{r.kind !== "serial" ? `:${r.port}` : ""}
                          {r.username ? ` · ${r.username}` : ""}
                          {r.group ? ` · ${r.group}` : ""}
                        </div>
                      </div>
                      <span className="pill no">{r.device_type}</span>
                      <span className="stat">—</span>
                    </div>
                  ))}
                </div>
                {imp.rows.length > 200 && (
                  <p className="stat">Showing the first 200 of {imp.rows.length}. All of them will be imported.</p>
                )}
              </>
            )}
          </>
        )}

        {tab === "about" && (
          <>
            <div className="set-cap"><h1>About NTerm</h1><span className="n">ValeronLabs LLC</span></div>
            <p style={{ color: "var(--muted)", margin: 0, maxWidth: "66ch" }}>
              Sessions, broadcast, syslog, TFTP, DHCP, analyzers, and a CCIE bench. Apache-2.0.
            </p>
            <div className="row">
              <img src="/icon.png" alt="NTerm" style={{ width: 48, height: 48, borderRadius: 12 }} />
              <div>
                <strong>NTerm</strong>
                <div style={{ color: "var(--muted)", fontSize: 12.5 }}>
                  nterm.ai · v{settings?.version || "0.1.0"}
                  {settings?.build && settings.build !== "dev" ? ` · build ${settings.build}` : ""}
                </div>
              </div>
            </div>
            <div className="row">
              <a className="primary" href="https://nterm.ai" target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>nterm.ai</a>
              <a className="ghost" href="https://github.com/devnexthop/nterm.ai" target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>GitHub</a>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
