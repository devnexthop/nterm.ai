import { useEffect, useMemo, useState, type MouseEvent } from "react";
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
import SnippetBar from "./components/SnippetBar";
import EditorDrawer from "./components/EditorDrawer";
import DoBar from "./components/DoBar";

type Page = "sessions" | "toolkit" | "bench" | "settings";
type Layout = "single" | "split" | "quad";

function uid() {
  return crypto.randomUUID();
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
  const [dragTab, setDragTab] = useState<string | null>(null);
  const [broadcast, setBroadcast] = useState("");
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
  const chrome = applyTheme(settings?.theme || "nexthop_dark");

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
            <button className="ghost" onClick={() => setSubnetOpen(true)}>Subnet</button>
            <button className="ghost" onClick={() => setAiOpen((v) => !v)}
              title={(aiOpen ? "Hide" : "Show") + " AI panel  (\u2318\u21e7A)"}>
              {aiOpen ? "Hide AI \u203a" : "\u2039 Show AI"}
            </button>
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
        <div className={`workspace ${aiOpen ? "" : "no-ai"} ${editor ? "with-edit" : ""}`}>
          <Sidebar
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
          />
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
            <div className="tabs">
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
                    <TerminalPane
                      tab={t}
                      theme={THEMES.find((x) => x.id === settings?.theme) || THEMES[0]}
                      fontSize={settings?.font_size || 14}
                      active={t.tabId === active}
                      onEditText={(text, title) => setEditor({ text, title })}
                      onAskAi={askAi}
                    />
                  </div>
                ))}
              </div>
            )}
            <DoBar
              tab={activeTab}
              usage={usage}
              onUsage={loadUsage}
              onEdit={(text, title) => setEditor({ text, title })}
            />
            <SnippetBar
              snippets={deviceSnips}
              pack={snipPack}
              onPack={setSnipPack}
              tabId={activeTab?.tabId}
              onAdd={() => setSnipForm({ name: "", command: "", device_types: dtype ? [dtype] : [] })}
              onEdit={(s) => setSnipForm({ id: s.id, name: s.name, command: s.command, device_types: s.device_types })}
              onDelete={async (s) => {
                if (!s.id) return;
                await api(`/api/snippets/${s.id}`, { method: "DELETE" });
                refresh();
              }}
            />
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
            {subnetOpen && <SubnetOverlay onClose={() => setSubnetOpen(false)} />}
          </section>
          {aiOpen && <AiPanel tab={activeTab} ask={aiAsk} />}
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
