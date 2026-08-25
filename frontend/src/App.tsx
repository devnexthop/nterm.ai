import { useEffect, useMemo, useState, type MouseEvent } from "react";
import { api } from "./api";
import type { Customer, OpenTab, SavedSession, Settings, Snippet } from "./types";
import { applyTheme, THEMES } from "./themes";
import Sidebar from "./components/Sidebar";
import TerminalPane, { sendToTab } from "./components/TerminalPane";
import AiPanel from "./components/AiPanel";
import Toolkit from "./components/Toolkit";
import Bench from "./components/Bench";
import SettingsPage from "./components/Settings";
import { CustomerForm, Palette, SessionForm } from "./components/Dialogs";

type Page = "sessions" | "toolkit" | "bench" | "settings";
type Layout = "single" | "split" | "quad";

function uid() {
  return crypto.randomUUID();
}

export default function App() {
  const [page, setPage] = useState<Page>("sessions");
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [tabs, setTabs] = useState<OpenTab[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [layout, setLayout] = useState<Layout>("single");
  const [aiOpen, setAiOpen] = useState(true);
  const [broadcast, setBroadcast] = useState("");
  const [scope, setScope] = useState<"selected" | "customer" | "all">("selected");
  const [palette, setPalette] = useState(false);
  const [newCust, setNewCust] = useState(false);
  const [sessForm, setSessForm] = useState<{ customer?: Customer; session?: SavedSession } | null>(null);
  const [snippets, setSnippets] = useState<Snippet[]>([]);
  const chrome = applyTheme(settings?.theme || "nexthop_dark");

  async function refresh() {
    setCustomers(await api("/api/customers"));
    const s = await api<Settings>("/api/settings");
    setSettings(s);
    applyTheme(s.theme);
    const meta = await api<{ snippets: Snippet[] }>("/api/meta");
    setSnippets(meta.snippets);
  }

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

  async function sendBroadcast() {
    const targets = targetTabs();
    for (const t of targets) sendToTab(t.tabId, broadcast.endsWith("\n") ? broadcast : broadcast + "\n");
    setBroadcast("");
  }

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
  const deviceSnips = snippets.filter((s) => {
    if (!activeTab) return true;
    return true;
  }).slice(0, 8);

  const paletteItems = [
    ...customers.flatMap((c) => c.sessions.map((s) => ({
      label: `Open ${c.name} / ${s.name}`,
      run: () => openSession(c, s),
    }))),
    { label: "New customer", run: () => setNewCust(true) },
    { label: "New session", run: () => setSessForm({}) },
    { label: "Go to toolkit", run: () => setPage("toolkit") },
    { label: "Go to engineer bench", run: () => setPage("bench") },
    { label: "Go to settings", run: () => setPage("settings") },
    { label: "Split panes", run: () => setLayout("split") },
    { label: "Merge to single tab", run: () => setLayout("single") },
    { label: "Quad tiles", run: () => setLayout("quad") },
    { label: "Toggle AI", run: () => setAiOpen((v) => !v) },
  ];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><img src="/icon.png" alt="" />NTerm</div>
        <nav>
          <button className={page === "sessions" ? "active" : ""} onClick={() => setPage("sessions")}>Sessions</button>
          <button className={page === "toolkit" ? "active" : ""} onClick={() => setPage("toolkit")}>Toolkit</button>
          <button className={page === "bench" ? "active" : ""} onClick={() => setPage("bench")}>Bench</button>
          <button className={page === "settings" ? "active" : ""} onClick={() => setPage("settings")}>Settings</button>
        </nav>
        <div className="spacer" />
        {page === "sessions" && (
          <>
            <button className="ghost" onClick={() => setLayout("single")}>Merge</button>
            <button className="ghost" onClick={() => setLayout("split")}>Split</button>
            <button className="ghost" onClick={() => setLayout("quad")}>Quad</button>
            <button className="ghost" onClick={() => setAiOpen((v) => !v)}>AI</button>
          </>
        )}
        <span className="kbd">⌘K</span>
        <button className="ghost" onClick={() => setPalette(true)}>Palette</button>
      </header>

      {page === "toolkit" && <Toolkit />}
      {page === "bench" && <Bench />}
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
        <div className={`workspace ${aiOpen ? "" : "no-ai"}`}>
          <Sidebar
            customers={customers}
            onOpen={openSession}
            onNewCustomer={() => setNewCust(true)}
            onNewSession={(c) => setSessForm({ customer: c })}
            onEditSession={(c, s) => setSessForm({ customer: c, session: s })}
          />
          <section className="main">
            <div className="tabs">
              {tabs.map((t) => (
                <div
                  key={t.tabId}
                  className={`tab ${t.tabId === active ? "active" : ""} ${t.selected ? "picked" : ""}`}
                  onClick={(e) => toggleSelect(t.tabId, e)}
                >
                  <span className="dot" style={{ background: customers.find((c) => c.name === t.customerName)?.color || chrome.accent }} />
                  {t.customerName} · {t.session.name}
                  <button className="close" onClick={(e) => { e.stopPropagation(); closeTab(t.tabId); }}>×</button>
                </div>
              ))}
              <button className="ghost" onClick={() => setSessForm({})}>+ Tab</button>
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
                    <TerminalPane tab={t} theme={THEMES.find((x) => x.id === settings?.theme) || THEMES[0]} fontSize={settings?.font_size || 14} active={t.tabId === active} />
                  </div>
                ))}
              </div>
            )}
            <div className="snippets">
              {deviceSnips.map((s) => (
                <button key={s.name} className="chip" onClick={() => {
                  for (const t of targetTabs()) sendToTab(t.tabId, s.command + (s.command.includes("\n") ? "" : "\n"));
                }}>{s.name}</button>
              ))}
            </div>
            <div className="broadcast">
              <select value={scope} onChange={(e) => setScope(e.target.value as any)}>
                <option value="selected">Selected tabs</option>
                <option value="customer">This customer</option>
                <option value="all">All tabs</option>
              </select>
              <input
                id="broadcast"
                value={broadcast}
                onChange={(e) => setBroadcast(e.target.value)}
                placeholder="Broadcast a command — like SecureCRT chat, but faster"
                onKeyDown={(e) => { if (e.key === "Enter") sendBroadcast(); }}
              />
              <button className="primary" onClick={sendBroadcast}>Send</button>
            </div>
          </section>
          {aiOpen && <AiPanel tab={activeTab} />}
        </div>
      )}

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
    </div>
  );
}
