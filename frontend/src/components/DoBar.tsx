import { useState } from "react";
import { api } from "../api";
import type { AiPreview, OpenTab, TokenUsage } from "../types";
import { getBuffer, sendToTab } from "./TerminalPane";

export default function DoBar({
  tab,
  usage,
  onUsage,
  onEdit,
}: {
  tab?: OpenTab;
  usage: TokenUsage | null;
  onUsage: () => void;
  onEdit: (text: string, title: string) => void;
}) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [preview, setPreview] = useState<AiPreview | null>(null);

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
      if (res.risk === "low" && res.tool === "show_status" && tab) {
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
      for (const cmd of p.commands) {
        sendToTab(tab.tabId, cmd.endsWith("\n") ? cmd : cmd + "\n");
      }
    }
    setPreview(null);
    setQ("");
    onUsage();
  }

  const tok = usage ? `${(usage.today / 1000).toFixed(usage.today >= 1000 ? 1 : 0)}k tok today` : "";

  return (
    <div className="dobar">
      <div className="dobar-row">
        <span className="dobar-label">
          <svg className="dobar-spark" viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"
               fill="none" stroke="currentColor" strokeWidth="1.6"
               strokeLinecap="round" strokeLinejoin="round">
            <path className="spark-lg" d="M12 3.2 13.6 9.1 19.5 10.7 13.6 12.3 12 18.2 10.4 12.3 4.5 10.7 10.4 9.1Z" />
            <path className="spark-sm" d="M18.4 15.6 19 17.6 21 18.2 19 18.8 18.4 20.8 17.8 18.8 15.8 18.2 17.8 17.6Z" />
          </svg>
          <span>Do</span>
        </span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="set Loopback0 to 1.1.1.1/24"
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
        />
        <button className="primary" onClick={run} disabled={busy || !tab}>{busy ? "…" : "Propose"}</button>
        {tok && <span className="chip tok">{tok}</span>}
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
          <div className="row">
            <button className="primary" onClick={() => apply(preview, "confirmed")} disabled={!tab}>Confirm</button>
            <button className="ghost" onClick={() => onEdit(preview.commands.join("\n"), preview.summary)}>Edit</button>
            <button className="ghost" onClick={() => apply(preview, "discarded")}>Discard</button>
          </div>
        </div>
      )}
    </div>
  );
}
