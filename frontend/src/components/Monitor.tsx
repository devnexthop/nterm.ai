import { useEffect, useState } from "react";
import { api } from "../api";
import type { AiEvent, Customer, TokenUsage } from "../types";

export default function Monitor({ customers }: { customers: Customer[] }) {
  const [events, setEvents] = useState<AiEvent[]>([]);
  const [usage, setUsage] = useState<TokenUsage | null>(null);
  const [cid, setCid] = useState<string>("");
  const [decision, setDecision] = useState("");

  async function load() {
    const q = cid ? `?customer_id=${cid}` : "";
    setEvents(await api<AiEvent[]>(`/api/ai/events${q}`));
    setUsage(await api<TokenUsage>("/api/ai/usage"));
  }

  useEffect(() => { load(); }, [cid]);

  const rows = events.filter((e) => !decision || e.decision === decision);

  function csv() {
    const header = "id,created_at,customer_id,source,prompt,tool,decision,provider,model,tokens,cache_hit\n";
    const body = rows.map((e) =>
      [e.id, e.created_at, e.customer_id, e.source, JSON.stringify(e.prompt), e.tool_name, e.decision, e.provider, e.model, e.total_tokens, e.cache_hit].join(",")
    ).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([header + body], { type: "text/csv" }));
    a.download = "nterm-ai-monitor.csv";
    a.click();
  }

  return (
    <div className="page">
      <h1>AI Monitor</h1>
      <p className="hint">Local only — prompts, confirm/discard, and token totals stay in nterm.db on this machine. API keys are never logged.</p>
      <div className="row chips-row">
        <span className="chip">today {usage?.today ?? 0}</span>
        <span className="chip">7d {usage?.days_7 ?? 0}</span>
        <span className="chip">all {usage?.all ?? 0}</span>
        <span className="chip">{usage?.events ?? 0} events</span>
        <button className="ghost" onClick={csv}>Export CSV</button>
        <button className="ghost" onClick={async () => { await api("/api/ai/cache", { method: "DELETE" }); load(); }}>Clear LLM cache</button>
      </div>
      <div className="row" style={{ margin: "12px 0" }}>
        <select value={cid} onChange={(e) => setCid(e.target.value)}>
          <option value="">All customers</option>
          {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select value={decision} onChange={(e) => setDecision(e.target.value)}>
          <option value="">Any decision</option>
          <option value="proposed">proposed</option>
          <option value="confirmed">confirmed</option>
          <option value="discarded">discarded</option>
          <option value="edited">edited</option>
        </select>
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>When</th>
            <th>Customer</th>
            <th>Source</th>
            <th>Prompt</th>
            <th>Tool</th>
            <th>Decision</th>
            <th>Model</th>
            <th>Tok</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id}>
              <td>{e.created_at?.replace("T", " ").slice(0, 19)}</td>
              <td>{customers.find((c) => c.id === e.customer_id)?.name || "—"}</td>
              <td>{e.source}</td>
              <td title={e.commands_preview}>{e.prompt}</td>
              <td>{e.tool_name}{e.cache_hit ? " · cached" : ""}</td>
              <td className={`dec ${e.decision}`}>{e.decision}</td>
              <td>{e.provider}/{e.model}</td>
              <td>{e.total_tokens ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
