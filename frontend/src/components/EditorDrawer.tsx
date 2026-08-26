import { useEffect, useRef, useState } from "react";
import { api } from "../api";

export default function EditorDrawer({
  title,
  text,
  vendor,
  customerId,
  canSend,
  onClose,
  onSend,
  onAsk,
}: {
  title: string;
  text: string;
  vendor?: string;
  customerId?: number;
  canSend?: boolean;
  onClose: () => void;
  onSend: (text: string) => void;
  onAsk: (text: string) => void;
}) {
  const [body, setBody] = useState(text);
  const area = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { setBody(text); }, [text]);
  useEffect(() => { area.current?.focus(); }, []);

  async function saveKb() {
    await api("/api/kb", {
      method: "POST",
      body: JSON.stringify({ title, body, source: "editor_save", vendor: vendor || "", customer_id: customerId || null }),
    });
  }

  return (
    <aside className="editor-drawer">
      <div className="editor-head">
        <strong>{title}</strong>
        <span className="spacer" />
        <button className="ghost" onClick={() => onAsk(body)} disabled={!body.trim()}>Ask AI</button>
        <button className="primary" onClick={() => onSend(body)} disabled={!canSend || !body.trim()}>Send to session</button>
        <button className="ghost" onClick={saveKb}>Save to KB</button>
        <button className="ghost" onClick={onClose}>Close</button>
      </div>
      <textarea
        ref={area}
        className="editor-host"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        spellCheck={false}
      />
    </aside>
  );
}
