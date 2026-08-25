import { useState } from "react";
import { api } from "../api";
import type { OpenTab } from "../types";
import { getBuffer, sendToTab } from "./TerminalPane";

export default function AiPanel({ tab }: { tab?: OpenTab }) {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<{ role: "user" | "bot"; text: string }[]>([
    {
      role: "bot",
      text: "Paste an OpenAI key in Settings to go live. I can already suggest built-in snippets and read this session once you ask.",
    },
  ]);

  async function send() {
    if (!msg.trim()) return;
    const text = msg;
    setMsg("");
    setLog((l) => [...l, { role: "user", text }]);
    setBusy(true);
    try {
      const res = await api<{ reply: string }>("/api/ai/chat", {
        method: "POST",
        body: JSON.stringify({
          message: text,
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
          placeholder="Why is Gi0/2 down? Draft a hardening snippet…"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
          }}
        />
        <button className="primary" onClick={send} disabled={busy}>{busy ? "…" : "Ask"}</button>
      </div>
    </aside>
  );
}
