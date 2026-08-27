import { useEffect, useMemo, useState, type MouseEvent, type ReactNode } from "react";
import { api } from "./api";
import type { Customer, OpenTab, SavedSession, Settings, Snippet, TokenUsage } from "./types";
import { applyTheme, THEMES } from "./themes";
import Sidebar from "./components/Sidebar";
import TerminalPane, { sendToTab } from "./components/TerminalPane";
import AiPanel from "./components/AiPanel";
import Toolkit from "./components/Toolkit";
import Bench from "./components/Bench";
import SettingsPage from "./components/Settings";
import { CustomerForm, Palette, SessionForm, SnippetForm } from "./components/Dialogs";
import SubnetOverlay from "./components/SubnetOverlay";
import EditorDrawer from "./components/EditorDrawer";
import Monitor from "./components/Monitor";
import CommandBar, { type Mode } from "./components/CommandBar";
import ErrorBoundary from "./components/ErrorBoundary";

type Page = "sessions" | "toolkit" | "bench" | "monitor" | "settings";
type Layout = "single" | "split" | "quad";

function uid() {
  return crypto.randomUUID();
}

/** Bottom-bar visibility, remembered per browser. Each bar costs terminal
 *  height, so the choice should survive a reload. */
function usePref(key: string, fallback: boolean): [boolean, (v: boolean | ((p: boolean) => boolean)) => void] {
  const [val, setVal] = useState<boolean>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? fallback : raw === "1";
    } catch {
      return fallback;
    }
  });
  const set = (v: boolean | ((p: boolean) => boolean)) =>
    setVal((prev) => {
      const next = typeof v === "function" ? (v as (p: boolean) => boolean)(prev) : v;
      try { localStorage.setItem(key, next ? "1" : "0"); } catch {}
      return next;
    });
  return [val, set];
}

/** Same idea as usePref, for the command bar's mode. */
function usePrefStr<T extends string>(key: string, fallback: T): [T, (v: T) => void] {
  const [val, setVal] = useState<T>(() => {
    try { return (localStorage.getItem(key) as T) || fallback; } catch { return fallback; }
  });
  const set = (v: T) => {
    setVal(v);
    try { localStorage.setItem(key, v); } catch {}
  };
  return [val, set];
}

export default function App() {
  const [page, setPage] = useState<Page>("sessions");
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [usage, setUsage] = useState<TokenUsage | null>(null);
  const loadUsage = () => api<TokenUsage>("/api/ai/usage").then(setUsage).catch(() => {});
  const [tabs, setTabs] = useState<OpenTab[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [layout, setLayout] = useState<Layout>("single");
  const [aiOpen, setAiOpen] = useState(true);
  const [sideOpen, setSideOpen] = useState(true);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [shareBusy, setShareBusy] = useState(false);
  const [barMode, setBarMode] = usePrefStr<Mode>("nterm.bar.mode", "do");

  async function toggleShare() {
    if (!activeTab) return;
    setShareBusy(true);
    try {
      if (shareUrl) {
        await api(`/api/share/${activeTab.tabId}`, { method: "DELETE" });
        setShareUrl(null);
      } else {
        const r = await api<{ url: string }>(`/api/share/${activeTab.tabId}`, { method: "POST" });
        setShareUrl(r.url);
      }
    } catch (e: any) {
      window.alert(e.message || String(e));
    } finally {
      setShareBusy(false);
    }
  }
  const [dragTab, setDragTab] = useState<string | null>(null);
  const [dropOn, setDropOn] = useState(false);
  const [scope, setScope] = useState<"selected" | "customer" | "all">("selected");
  const [palette, setPalette] = useState(false);
  const [newCust, setNewCust] = useState(false);
  const [sessForm, setSessForm] = useState<{ customer?: Customer; session?: SavedSession } | null>(null);
  const [snippets, setSnippets] = useState<Snippet[]>([]);
  const [snipPack, setSnipPack] = useState("auto");
  const [snipForm, setSnipForm] = useState<{ id?: string; name: string; command: string; device_types?: string[] } | null>(null);
  const [editor, setEditor] = useState<{ title: string; text: string } | null>(null);
  const [aiAsk, setAiAsk] = useState<{ text: string; nonce: number } | null>(null);
  const [subnetOpen, setSubnetOpen] = useState(false);
  const chrome = applyTheme(settings?.theme || "valeron");

  async function refresh() {
    setCustomers(await api("/api/customers"));
    const s = await api<Settings>("/api/settings");
    setSettings(s);
    applyTheme(s.theme);
    const meta = await api<{ snippets: Snippet[] }>("/api/meta");
    setSnippets(meta.snippets);
  }

  useEffect(() => { loadUsage(); }, []);

  useEffect(() => { refresh(); }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette(true); }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "n") { e.preventDefault(); setSessForm({}); }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        document.getElementById("broadcast")?.focus();
      }
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "a") { e.preventDefault(); setAiOpen((v) => !v); }
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "s") { e.preventDefault(); setSideOpen((v) => !v); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function openSession(c: Customer, s: SavedSession) {
    const tab: OpenTab = { tabId: uid(), session: s, customerName: c.name, selected: true };
    setTabs((t) => [...t, tab]);
    setActive(tab.tabId);
    setPage("sessions");
  }

  function closeTab(id: string) {
    setTabs((t) => t.filter((x) => x.tabId !== id));
    if (active === id) setActive(tabs.find((x) => x.tabId !== id)?.tabId || null);
  }

  function toggleSelect(id: string, ev: MouseEvent) {
    if (ev.shiftKey || ev.metaKey || ev.ctrlKey) {
      setTabs((t) => t.map((x) => x.tabId === id ? { ...x, selected: !x.selected } : x));
    } else {
      setActive(id);
    }
  }

  const visible = useMemo(() => {
    if (layout === "single") return tabs.filter((t) => t.tabId === active).slice(0, 1);
    if (layout === "split") return tabs.slice(-2);
    return tabs.slice(-4);
  }, [tabs, active, layout]);

  function targetTabs() {
    if (scope === "all") return tabs;
    if (scope === "customer") {
      const cur = tabs.find((t) => t.tabId === active);
      return tabs.filter((t) => t.customerName === cur?.customerName);
    }
    const picked = tabs.filter((t) => t.selected);
    return picked.length ? picked : tabs.filter((t) => t.tabId === active);
  }

  const activeTab = tabs.find((t) => t.tabId === active);
  const dtype = activeTab?.session.device_type;
  const deviceSnips = snippets.filter((s) => {
    const types = s.device_types || [];
    if (snipPack === "all") return true;
    if (snipPack === "user-snippets") return Boolean(s.editable);
    if (snipPack !== "auto") return s.extension === snipPack;
    if (s.editable) return !types.length || !dtype || types.includes(dtype);
    return !dtype || types.includes(dtype) || !types.length;
  });

  function askAi(text: string) {
    setAiOpen(true);
    setAiAsk({ text, nonce: Date.now() });
  }

  async function saveChip(body: { id?: string; name: string; command: string; device_types: string[] }) {
    if (body.id) {
      await api(`/api/snippets/${body.id}`, { method: "PUT", body: JSON.stringify(body) });
    } else {
      await api("/api/snippets", { method: "POST", body: JSON.stringify(body) });
    }
    setSnipForm(null);
    if (body.device_types.length === 0) setSnipPack("user-snippets");
    refresh();
  }

  const paletteItems = [
    ...customers.flatMap((c) => c.sessions.map((s) => ({
      label: `Open ${c.name} / ${s.name}`,
      run: () => openSession(c, s),
    }))),
    { label: "New customer", run: () => setNewCust(true) },
    { label: "New session", run: () => setSessForm({}) },
    { label: "Subnet calculator", run: () => { setPage("sessions"); setSubnetOpen(true); } },
    { label: "Go to toolkit", run: () => setPage("toolkit") },
    { label: "Go to engineer bench", run: () => setPage("bench") },
    { label: "Go to settings", run: () => setPage("settings") },
    { label: "Split panes", run: () => setLayout("split") },
    { label: "Merge to single tab", run: () => setLayout("single") },
    { label: "Quad tiles", run: () => setLayout("quad") },
    { label: "Toggle AI", run: () => setAiOpen((v) => !v) },
    { label: "Toggle sessions sidebar", run: () => setSideOpen((v) => !v) },
    { label: "Command bar: Do", run: () => { setPage("sessions"); setBarMode("do"); } },
    { label: "Command bar: Cast (broadcast)", run: () => { setPage("sessions"); setBarMode("cast"); } },
    { label: "Command bar: Macros", run: () => { setPage("sessions"); setBarMode("chips"); } },
    { label: "Go to AI monitor", run: () => setPage("monitor") },
    { label: "Share this session", run: () => toggleShare() },
  ];

  const RAIL: { id: Page; label: string; icon: ReactNode }[] = [
    { id: "sessions", label: "Sessions", icon: (
      <svg viewBox="0 0 24 24"><rect x="2" y="4" width="20" height="16" rx="2" /><path d="m6 9 3 3-3 3M13 15h5" /></svg>) },
    { id: "toolkit", label: "Toolkit", icon: (
      <svg viewBox="0 0 24 24"><path d="M14.7 6.3a4 4 0 0 0 5 5l-9.6 9.6a2 2 0 0 1-3-3Z" /><path d="M18 2 22 6" /></svg>) },
    { id: "bench", label: "Bench", icon: (
      <svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" /></svg>) },
    { id: "monitor", label: "Monitor", icon: (
      <svg viewBox="0 0 24 24"><path d="M3 12h4l3 8 4-16 3 8h4" /></svg>) },
  ];

  return (
    <div className="app">
      {/* Navigation is not a session action, so it leaves the top row entirely.
          This also finally gives Monitor a home — it existed as a component
          with no route at all. */}
      <nav className="railnav" aria-label="Main">
        <img className="rail-mk" src="/icon.png" alt="NTerm" />
        {RAIL.map((r) => (
          <button
            key={r.id}
            className={`ritem ${page === r.id ? "on" : ""}`}
            onClick={() => setPage(r.id)}
            aria-current={page === r.id ? "page" : undefined}
            title={r.label}
          >
            <span className="rp">{r.icon}</span>
            <span>{r.label}</span>
          </button>
        ))}
        <span className="rail-grow" />
        <button
          className={`ritem ${page === "settings" ? "on" : ""}`}
          onClick={() => setPage("settings")}
          aria-current={page === "settings" ? "page" : undefined}
          title="Settings"
        >
          <span className="rp">
            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" /><path d="M20 12a8 8 0 0 1-.2 1.8l2 1.5-2 3.4-2.3-1a8 8 0 0 1-3 1.8L14 22h-4l-.5-2.5a8 8 0 0 1-3-1.8l-2.3 1-2-3.4 2-1.5a8 8 0 0 1 0-3.6l-2-1.5 2-3.4 2.3 1a8 8 0 0 1 3-1.8L10 2h4l.5 2.5a8 8 0 0 1 3 1.8l2.3-1 2 3.4-2 1.5c.13.58.2 1.18.2 1.8Z" /></svg>
          </span>
          <span>Settings</span>
        </button>
      </nav>

      <div className={`app-body ${page === "sessions" ? "" : "no-header"}`}>
        {/* Only active-session concerns live here. Share and Subnet act on the
            session in front of you, so they sit beside its hostname. */}
        {page === "sessions" && (
          <header className={`sesshdr ${activeTab ? "live" : ""}`}>
            <span className={`sh-led ${activeTab ? "" : "off"}`} />
            <span className="sh-host">{activeTab ? activeTab.session.name : "No session open"}</span>
            {activeTab && <span className="sh-chip">{activeTab.customerName}</span>}
            {activeTab?.session.device_type && <span className="sh-chip">{activeTab.session.device_type}</span>}
            <span className="sh-sp" />
            <button
              className={`sh-btn ${shareUrl ? "on" : ""}`}
              onClick={toggleShare}
              disabled={!activeTab || shareBusy}
              title={shareUrl ? "Stop sharing this session" : "Share this session read-only"}
            >
              {shareBusy ? "…" : shareUrl ? "Sharing" : "Share"}
            </button>
            <button className="sh-btn" onClick={() => setSubnetOpen(true)}>Subnet</button>
            <span className="sh-hint">⌘K</span>
          </header>
        )}

        {page === "toolkit" && <Toolkit />}
        {page === "bench" && <Bench />}
        {page === "monitor" && <Monitor customers={customers} />}
        {page === "settings" && (
          <SettingsPage
            settings={settings}
            onSave={async (patch) => {
              const next = await api<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(patch) });
              setSettings(next);
              applyTheme(next.theme);
            }}
          />
        )}

        {page === "sessions" && (
          <div className={`workspace ${aiOpen ? "" : "no-ai"} ${sideOpen ? "" : "no-side"} ${editor ? "with-edit" : ""}`}>
            {sideOpen && <Sidebar
              customers={customers}
              onOpen={openSession}
              onNewCustomer={() => setNewCust(true)}
              onNewSession={(c) => setSessForm({ customer: c })}
              onEditSession={(c, s) => setSessForm({ customer: c, session: s })}
              onDuplicate={async (s) => { await api(`/api/sessions/${s.id}/duplicate`, { method: "POST" }); refresh(); }}
              onVault={async (s) => {
                const name = window.prompt("Save as credential", `${s.name} vault`);
                if (!name) return;
                await api(`/api/sessions/${s.id}/vault`, { method: "POST", body: JSON.stringify({ name }) });
                refresh();
              }}
              onDelete={async (s) => {
                if (!window.confirm(`Delete session ${s.name}?`)) return;
                await api(`/api/sessions/${s.id}`, { method: "DELETE" });
                refresh();
              }}
              onQuickConnect={() => setSessForm({})}
            />}
            {editor && (
              <EditorDrawer
                title={editor.title}
                text={editor.text}
                vendor={activeTab?.session.device_type}
                customerId={activeTab?.session.customer_id}
                canSend={Boolean(activeTab)}
                onClose={() => setEditor(null)}
                onSend={(text) => {
                  if (activeTab) sendToTab(activeTab.tabId, text.endsWith("\n") ? text : text + "\n");
                }}
                onAsk={(text) => askAi(`What is this?\n\n${text}`)}
              />
            )}
            <section className="main">
              <div
                className={`tabs ${dropOn ? "drop-on" : ""}`}
                onDragOver={(e) => {
                  if (!e.dataTransfer.types.includes("application/x-nterm-session")) return;
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "copy";
                  setDropOn(true);
                }}
                onDragLeave={(e) => {
                  if (e.currentTarget.contains(e.relatedTarget as Node)) return;
                  setDropOn(false);
                }}
                onDrop={(e) => {
                  const raw = e.dataTransfer.getData("application/x-nterm-session");
                  setDropOn(false);
                  if (!raw) return;
                  e.preventDefault();
                  try {
                    const { customerId, sessionId } = JSON.parse(raw);
                    const c = customers.find((x) => x.id === customerId);
                    const sess = c?.sessions.find((x) => x.id === sessionId);
                    if (c && sess) openSession(c, sess);
                  } catch { /* malformed payload — ignore rather than crash the strip */ }
                }}
              >
                {tabs.map((t) => (
                  <div
                    key={t.tabId}
                    className={`tab ${t.tabId === active ? "active" : ""} ${t.selected ? "picked" : ""} ${dragTab === t.tabId ? "dragging" : ""}`}
                    onClick={(e) => toggleSelect(t.tabId, e)}
                    draggable
                    onDragStart={(e) => { setDragTab(t.tabId); e.dataTransfer.effectAllowed = "move"; }}
                    onDragEnd={() => setDragTab(null)}
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.dataTransfer.dropEffect = "move";
                      if (!dragTab || dragTab === t.tabId) return;
                      setTabs((prev) => {
                        const from = prev.findIndex((x) => x.tabId === dragTab);
                        const to = prev.findIndex((x) => x.tabId === t.tabId);
                        if (from < 0 || to < 0 || from === to) return prev;
                        const next = prev.slice();
                        next.splice(to, 0, next.splice(from, 1)[0]);
                        return next;
                      });
                    }}
                    onDrop={(e) => { e.preventDefault(); setDragTab(null); }}
                    title="Drag to reorder"
                  >
                    <span className="dot" style={{ background: customers.find((c) => c.name === t.customerName)?.color || chrome.accent }} />
                    {t.customerName} · {t.session.name}
                    <button className="close" onClick={(e) => { e.stopPropagation(); closeTab(t.tabId); }}>×</button>
                  </div>
                ))}
                <button className="tab-add" onClick={() => setSessForm({})}>+ Tab</button>
                {/* Layout acts on tabs, so it lives with the tabs — and unlike
                    three loose buttons, a segmented control shows which is on. */}
                <div className="layout-seg" role="group" aria-label="Pane layout">
                  {(["single", "split", "quad"] as Layout[]).map((l) => (
                    <button
                      key={l}
                      className={layout === l ? "on" : ""}
                      onClick={() => setLayout(l)}
                      aria-pressed={layout === l}
                    >
                      {l === "single" ? "Merge" : l === "split" ? "Split" : "Quad"}
                    </button>
                  ))}
                </div>
              </div>

              {tabs.length === 0 ? (
                <div className="empty">
                  <div>
                    <h2>Open a session</h2>
                    <p>Lab simulators work offline. Real SSH remembers user/password per customer.</p>
                  </div>
                </div>
              ) : (
                <div className={`panes ${layout}`}>
                  {visible.map((t) => (
                    <div className="pane" key={t.tabId} onClick={() => setActive(t.tabId)}>
                      <ErrorBoundary label={`${t.customerName} · ${t.session.name}`}>
                        <TerminalPane
                          tab={t}
                          theme={THEMES.find((x) => x.id === settings?.theme) || THEMES[0]}
                          fontSize={settings?.font_size || 14}
                          fontFamily={settings?.font_family}
                          active={t.tabId === active}
                          onEditText={(text, title) => setEditor({ text, title })}
                          onAskAi={askAi}
                        />
                      </ErrorBoundary>
                    </div>
                  ))}
                </div>
              )}

              {shareUrl && (
                <div className="share-banner">
                  <span className="share-dot" />
                  <strong>SHARING</strong>
                  <span className="share-note">read-only · anyone with the link can watch this session</span>
                  <code>{shareUrl}</code>
                  <button className="ghost" onClick={() => navigator.clipboard?.writeText(shareUrl)}>Copy</button>
                  <button className="ghost" onClick={toggleShare} disabled={shareBusy}>Stop</button>
                </div>
              )}

              {/* One bar where four used to stack. */}
              <CommandBar
                mode={barMode}
                onMode={setBarMode}
                tab={activeTab}
                usage={usage}
                onUsage={loadUsage}
                onEdit={(text, title) => setEditor({ text, title })}
                snippets={deviceSnips}
                pack={snipPack}
                onPack={setSnipPack}
                onAddChip={() => setSnipForm({ name: "", command: "", device_types: dtype ? [dtype] : [] })}
                onEditChip={(s) => setSnipForm({ id: s.id, name: s.name, command: s.command, device_types: s.device_types })}
                onDeleteChip={async (s) => {
                  if (!s.id) return;
                  await api(`/api/snippets/${s.id}`, { method: "DELETE" });
                  refresh();
                }}
                scope={scope}
                onScope={setScope}
                castTargets={targetTabs().length}
                onCast={(text) => {
                  if (!text.trim()) return;
                  for (const t of targetTabs()) sendToTab(t.tabId, text.endsWith("\n") ? text : text + "\n");
                }}
              />

              {subnetOpen && <SubnetOverlay onClose={() => setSubnetOpen(false)} />}
            </section>
            {aiOpen && <AiPanel tab={activeTab} ask={aiAsk} />}
          </div>
        )}
      </div>

      <Palette open={palette} onClose={() => setPalette(false)} items={paletteItems} />
      {newCust && (
        <CustomerForm
          onClose={() => setNewCust(false)}
          onSave={async (name, color) => {
            await api("/api/customers", { method: "POST", body: JSON.stringify({ name, color, notes: "" }) });
            setNewCust(false);
            refresh();
          }}
        />
      )}
      {sessForm && (
        <SessionForm
          customers={customers}
          customer={sessForm.customer}
          session={sessForm.session}
          onClose={() => setSessForm(null)}
          onSave={async (body) => {
            if (sessForm.session) {
              await api(`/api/sessions/${sessForm.session.id}`, { method: "PUT", body: JSON.stringify(body) });
            } else {
              await api("/api/sessions", { method: "POST", body: JSON.stringify(body) });
            }
            setSessForm(null);
            refresh();
          }}
        />
      )}
      {snipForm && (
        <SnippetForm
          snippet={snipForm}
          defaultVendor={dtype}
          onClose={() => setSnipForm(null)}
          onSave={saveChip}
        />
      )}
    </div>
  );
}
