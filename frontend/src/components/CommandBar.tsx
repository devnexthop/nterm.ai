import { useState, type MouseEvent } from "react";
import { api } from "../api";
import type { AiPreview, MenuItem, OpenTab, Snippet, TokenUsage } from "../types";
import { getBuffer, sendToTab } from "./TerminalPane";
import ContextMenu from "./ContextMenu";

const PACKS = [
  { id: "auto", label: "Auto (this session)" },
  { id: "cisco-essentials", label: "Cisco" },
  { id: "palo-essentials", label: "Palo Alto" },
  { id: "forti-essentials", label: "Fortinet" },
  { id: "juniper-essentials", label: "Juniper" },
  { id: "user-snippets", label: "My macros" },
  { id: "all", label: "All vendors" },
];

export type Mode = "do" | "cast" | "chips";

/** One bar, three modes. This replaces DoBar + SnippetBar + the broadcast row,
 *  which used to stack below the terminal and each cost a row of height. */
export default function CommandBar({
  mode, onMode,
  tab, usage, onUsage, onEdit,
  snippets, pack, onPack, onAddChip, onEditChip, onDeleteChip,
  scope, onScope, castTargets, onCast,
}: {
  mode: Mode;
  onMode: (m: Mode) => void;
  tab?: OpenTab;
  usage: TokenUsage | null;
  onUsage: () => void;
  onEdit: (text: string, title: string) => void;
  snippets: Snippet[];
  pack: string;
  onPack: (id: string) => void;
  onAddChip: () => void;
  onEditChip: (s: Snippet) => void;
  onDeleteChip: (s: Snippet) => void;
  scope: "selected" | "customer" | "all";
  onScope: (s: "selected" | "customer" | "all") => void;
  castTargets: number;
  onCast: (text: string) => void;
}) {
  const [q, setQ] = useState("");
  const [cast, setCast] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [preview, setPreview] = useState<AiPreview | null>(null);
  const [menu, setMenu] = useState<{ x: number; y: number; items: MenuItem[] } | null>(null);

  async function run() {
    if (!q.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const res = await api<AiPreview>("/api/ai/act", {
        method: "POST",
        body: JSON.stringify({
          message: q,
          session_id: tab?.session.id,
          customer_id: tab?.session.customer_id,
          device_type: tab?.session.device_type || "cisco_ios",
          transcript: tab ? getBuffer(tab.tabId).slice(-4000) : "",
        }),
      });
      setPreview(res);
      // Auto-apply is only ever for read-only status on network gear, and only
      // when the gate had no objection.
      if (
        res.risk === "low" &&
        res.tool === "show_status" &&
        res.policy?.verdict !== "block" &&
        tab
      ) {
        await apply(res, "confirmed");
      }
      onUsage();
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function apply(p: AiPreview, decision: "confirmed" | "discarded" | "edited") {
    await api("/api/ai/decision", { method: "POST", body: JSON.stringify({ event_id: p.event_id, decision }) });
    if (decision === "confirmed" && tab) {
      for (const cmd of p.commands) sendToTab(tab.tabId, cmd.endsWith("\n") ? cmd : cmd + "\n");
    }
    setPreview(null);
    setQ("");
    onUsage();
  }

  function sendChip(s: Snippet) {
    if (!tab) return;
    sendToTab(tab.tabId, s.command.endsWith("\n") ? s.command : s.command + "\n");
  }

  function chipMenu(e: MouseEvent, s: Snippet) {
    e.preventDefault();
    e.stopPropagation();
    const items: MenuItem[] = [{ label: "Send to session", run: () => sendChip(s) }];
    if (s.editable) {
      items.push({ label: "Edit macro", run: () => onEditChip(s) });
      items.push({ label: "Delete", danger: true, run: () => onDeleteChip(s) });
    } else {
      items.push({ label: "Copy into my macros", run: () => onEditChip({ ...s, id: undefined, editable: true }) });
    }
    setMenu({ x: e.clientX, y: e.clientY, items });
  }

  const tok = usage ? `${(usage.today / 1000).toFixed(usage.today >= 1000 ? 1 : 0)}k tokens today` : "";

  return (
    <div className="cbar">
      <div className="cbar-row">
        <span className="cbar-modes" role="tablist" aria-label="Command bar mode">
          <button
            role="tab"
            aria-selected={mode === "do"}
            aria-label="Do — AI actions"
            title="Do — describe a change in English"
            className={`cbar-ai ${mode === "do" ? "on" : ""} ${busy ? "busy" : ""}`}
            onClick={() => onMode("do")}
          >
            <svg
              className="cbar-spark"
              viewBox="0 0 24 24"
              width="15"
              height="15"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path className="spark-lg" d="M12 3.2 13.6 9.1 19.5 10.7 13.6 12.3 12 18.2 10.4 12.3 4.5 10.7 10.4 9.1Z" />
              <path className="spark-sm" d="M18.4 15.6 19 17.6 21 18.2 19 18.8 18.4 20.8 17.8 18.8 15.8 18.2 17.8 17.6Z" />
            </svg>
          </button>
          <button role="tab" aria-selected={mode === "cast"} className={mode === "cast" ? "on" : ""} onClick={() => onMode("cast")}>Cast</button>
          <button role="tab" aria-selected={mode === "chips"} className={mode === "chips" ? "on" : ""} onClick={() => onMode("chips")} title="One-click saved commands for this vendor">Macros</button>
        </span>

        {mode === "do" && (
          <>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="set Loopback0 to 1.1.1.1/24"
              aria-label="Describe the change in English"
              onKeyDown={(e) => { if (e.key === "Enter") run(); }}
            />
            <button className="cbar-go" onClick={run} disabled={busy || !tab}>{busy ? "…" : "Propose"}</button>
            {tok && <span className="cbar-tok">{tok}</span>}
          </>
        )}

        {mode === "cast" && (
          <>
            <select value={scope} onChange={(e) => onScope(e.target.value as any)} aria-label="Broadcast scope">
              <option value="selected">Selected tabs</option>
              <option value="customer">This customer</option>
              <option value="all">All tabs</option>
            </select>
            <input
              value={cast}
              onChange={(e) => setCast(e.target.value)}
              placeholder="Broadcast one command to several sessions"
              aria-label="Command to broadcast"
              onKeyDown={(e) => { if (e.key === "Enter") { onCast(cast); setCast(""); } }}
            />
            <button className="cbar-go" onClick={() => { onCast(cast); setCast(""); }} disabled={!cast.trim()}>
              Send to {castTargets}
            </button>
          </>
        )}

        {mode === "chips" && (
          <div className="cbar-chips">
            <select value={pack} onChange={(e) => onPack(e.target.value)} aria-label="Vendor pack">
              {PACKS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
            {snippets.map((s) => (
              <button
                key={`${s.extension}-${s.id || s.name}`}
                className={`chip ${s.editable ? "mine" : ""}`}
                title={s.command}
                onClick={() => sendChip(s)}
                onContextMenu={(e) => chipMenu(e, s)}
              >
                {s.name}
              </button>
            ))}
            <button className="chip add" onClick={onAddChip}>+ macro</button>
          </div>
        )}
      </div>

      {err && <div className="dobar-err">{err}</div>}

      {preview && (
        <div className="dobar-preview">
          <div className="row">
            <strong>{preview.summary}</strong>
            <span className={`risk ${preview.risk}`}>{preview.risk}</span>
            {preview.cache_hit && <span className="chip">cached</span>}
            {preview.offline && <span className="chip">offline heuristic</span>}
            <span className="muted">{preview.dialect} · {preview.tool}</span>
          </div>
          <pre>{preview.commands.join("\n")}</pre>

          {preview.policy && preview.policy.verdict !== "allow" && (
            <div className={`gate gate-${preview.policy.verdict}`}>
              <strong>
                {preview.policy.verdict === "block"
                  ? "Blocked before you saw it"
                  : "Outside the permit list"}
              </strong>
              <ul>
                {[...preview.policy.blocked, ...preview.policy.warnings].slice(0, 6).map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
              <span className="gate-note">
                {preview.policy.verdict === "block"
                  ? "This draft cannot be sent. Edit it, or ask for a smaller change."
                  : "Nothing here matched a known-good shape for this platform. Read it carefully."}
              </span>
            </div>
          )}

          <div className="row">
            <button
              className="primary"
              onClick={() => apply(preview, "confirmed")}
              disabled={!tab || preview.policy?.verdict === "block"}
              title={preview.policy?.verdict === "block" ? "Blocked by the policy gate" : undefined}
            >Confirm</button>
            <button className="ghost" onClick={() => onEdit(preview.commands.join("\n"), preview.summary)}>Edit</button>
            <button className="ghost" onClick={() => apply(preview, "discarded")}>Discard</button>
          </div>
        </div>
      )}

      {menu && <ContextMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => setMenu(null)} />}
    </div>
  );
}
