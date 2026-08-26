import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { OpenTab } from "../types";
import { getBuffer, sendToTab } from "./TerminalPane";

export default function AiPanel({
  tab,
  ask,
}: {
  tab?: OpenTab;
  ask?: { text: string; nonce: number } | null;
}) {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<{ role: "user" | "bot"; text: string }[]>([
    {
      role: "bot",
      text: "Highlight output in the session, right-click, and ask what it is. Or type here. Paste an API key in Settings for a live model.",
    },
  ]);
  const lastNonce = useRef(0);

  async function send(text?: string) {
    const payload = (text ?? msg).trim();
    if (!payload) return;
    if (!text) setMsg("");
    setLog((l) => [...l, { role: "user", text: payload }]);
    setBusy(true);
    try {
      const res = await api<{ reply: string }>("/api/ai/chat", {
        method: "POST",
        body: JSON.stringify({
          message: payload,
          session_id: tab?.session.id,
          transcript: tab ? getBuffer(tab.tabId) : "",
          device_type: tab?.session.device_type || "generic",
          customer_name: tab?.customerName || "",
        }),
      });
      setLog((l) => [...l, { role: "bot", text: res.reply }]);
    } catch (e: any) {
      setLog((l) => [...l, { role: "bot", text: e.message }]);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!ask?.text || ask.nonce === lastNonce.current) return;
    lastNonce.current = ask.nonce;
    send(ask.text);
  }, [ask?.nonce]);

  function sendLastCommand() {
    const last = [...log].reverse().find((x) => x.role === "bot");
    if (!last || !tab) return;
    const match = last.text.match(/`([^`]+)`/);
    if (match) sendToTab(tab.tabId, match[1] + "\n");
  }

  return (
    <aside className="ai-panel">
      <div className="ai-head">
        AI · {tab ? `${tab.customerName} / ${tab.session.name}` : "no session"}
        <button className="ghost" onClick={sendLastCommand} disabled={!tab}>Send cmd</button>
      </div>
      <div className="ai-log">
        {log.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>{m.text}</div>
        ))}
      </div>
      <div className="ai-form">
        <textarea
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
          placeholder="Ask about the selection, or type a question…"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
          }}
        />
        <button className="primary" onClick={() => send()} disabled={busy}>{busy ? "…" : "Ask"}</button>
      </div>
    </aside>
  );
}
