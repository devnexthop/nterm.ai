import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";

type Action = { id: string; label: string; hint: string; prompt: (v: string, vendor: string) => string };

/* Transforms return the buffer, not conversation. Each prompt says "output only
   the result" because a model that helpfully wraps config in prose produces a
   buffer you cannot send to a device. */
const ACTIONS: Action[] = [
  {
    id: "explain", label: "Explain", hint: "What does this config do?",
    prompt: (v, vendor) =>
      `Explain what this ${vendor || "network"} configuration does, line by line, for a network engineer. ` +
      `Be concise. Flag anything risky.\n\n${v}`,
  },
  {
    id: "comment", label: "Comment", hint: "Annotate each block in place",
    prompt: (v, vendor) =>
      `Add inline comments to this ${vendor || "network"} configuration explaining each block. ` +
      `Keep every original line exactly as-is and in order. Use the correct comment character for the platform. ` +
      `Output ONLY the commented configuration, no prose, no code fences.\n\n${v}`,
  },
  {
    id: "tidy", label: "Tidy", hint: "Normalise order and indentation",
    prompt: (v, vendor) =>
      `Reformat this ${vendor || "network"} configuration: consistent indentation, grouped by section, ` +
      `duplicates removed. Do NOT change any value, address or keyword. ` +
      `Output ONLY the configuration, no prose, no code fences.\n\n${v}`,
  },
  {
    id: "review", label: "Review", hint: "Find mistakes before you send it",
    prompt: (v, vendor) =>
      `Review this ${vendor || "network"} configuration for syntax errors, missing dependencies ` +
      `(an interface referenced but not defined, an ACL applied but not created), and anything that ` +
      `would drop your own management session. List findings only. If it is clean, say so.\n\n${v}`,
  },
];

const VENDORS = [
  ["cisco_ios", "Cisco IOS"], ["cisco_nxos", "Cisco NX-OS"], ["juniper", "Juniper"],
  ["arista_eos", "Arista EOS"], ["paloalto", "Palo Alto"], ["fortinet", "FortiOS"],
];

export default function EditorDrawer({
  title, text, vendor, customerId, canSend, onClose, onSend, onAsk,
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
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [readout, setReadout] = useState("");
  const [undo, setUndo] = useState<string | null>(null);
  const [convertTo, setConvertTo] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { setBody(text); setUndo(null); setReadout(""); }, [text]);
  useEffect(() => { area.current?.focus(); }, []);

  const lines = useMemo(() => body.split("\n").length, [body]);

  /** Selection if there is one, otherwise the whole buffer — the usual editor
   *  contract, so "Comment" on a highlighted block does not rewrite the file. */
  function scope(): { value: string; start: number; end: number } {
    const el = area.current;
    if (el && el.selectionEnd > el.selectionStart) {
      return { value: body.slice(el.selectionStart, el.selectionEnd), start: el.selectionStart, end: el.selectionEnd };
    }
    return { value: body, start: 0, end: body.length };
  }

  async function ask(prompt: string): Promise<string> {
    const r = await api<{ reply: string }>("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({
        message: prompt,
        device_type: vendor || "generic",
        customer_name: "",
        transcript: "",
      }),
    });
    // Models add fences even when told not to; strip them rather than ship them.
    return (r.reply || "").replace(/^```[a-z]*\n?/i, "").replace(/\n?```\s*$/i, "").trim();
  }

  async function run(a: Action) {
    const sel = scope();
    if (!sel.value.trim()) return;
    setBusy(a.id); setNote(""); setReadout("");
    try {
      const out = await ask(a.prompt(sel.value, vendor || ""));
      if (a.id === "explain" || a.id === "review") {
        setReadout(out);
      } else {
        setUndo(body);
        setBody(body.slice(0, sel.start) + out + body.slice(sel.end));
        setNote(`${a.label} applied to ${sel.start === 0 && sel.end === body.length ? "the buffer" : "the selection"}`);
      }
    } catch (e: any) {
      setNote(e.message || String(e));
    } finally {
      setBusy("");
    }
  }

  async function convert() {
    if (!convertTo) return;
    const sel = scope();
    if (!sel.value.trim()) return;
    const label = VENDORS.find((v) => v[0] === convertTo)?.[1] || convertTo;
    setBusy("convert"); setNote(""); setReadout("");
    try {
      const out = await ask(
        `Translate this ${vendor || "network"} configuration into ${label} syntax. ` +
        `Preserve every address, name and value exactly. Where a feature has no direct equivalent, ` +
        `emit a comment saying so rather than inventing config. ` +
        `Output ONLY the ${label} configuration, no prose, no code fences.\n\n${sel.value}`,
      );
      setUndo(body);
      setBody(body.slice(0, sel.start) + out + body.slice(sel.end));
      setNote(`Converted to ${label} — check it before you send it.`);
    } catch (e: any) {
      setNote(e.message || String(e));
    } finally {
      setBusy("");
    }
  }

  async function saveKb() {
    await api("/api/kb", {
      method: "POST",
      body: JSON.stringify({ title, body, source: "editor_save", vendor: vendor || "", customer_id: customerId || null }),
    });
    setNote("Saved to the knowledge base");
  }

  return (
    <aside className="editor-drawer">
      <div className="editor-head">
        <strong>{title}</strong>
        <span className="ed-meta">{lines} line{lines === 1 ? "" : "s"}{vendor ? ` · ${vendor.replace("_", " ")}` : ""}</span>
        <span className="spacer" />
        <button className="primary" onClick={() => onSend(body)} disabled={!canSend || !body.trim()}>Send to session</button>
        <button className="ghost" onClick={saveKb}>Save to KB</button>
        <button className="ghost" onClick={onClose}>Close</button>
      </div>

      <div className="editor-ai">
        {ACTIONS.map((a) => (
          <button key={a.id} className="chip" title={a.hint} disabled={!!busy || !body.trim()} onClick={() => run(a)}>
            {busy === a.id ? "…" : a.label}
          </button>
        ))}
        <select value={convertTo} onChange={(e) => setConvertTo(e.target.value)} title="Translate to another vendor">
          <option value="">Convert to…</option>
          {VENDORS.filter((v) => v[0] !== vendor).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>
        <button className="chip" disabled={!convertTo || !!busy} onClick={convert}>
          {busy === "convert" ? "…" : "Go"}
        </button>
        <span className="spacer" />
        {undo && <button className="ghost" onClick={() => { setBody(undo); setUndo(null); setNote("Reverted"); }}>Undo</button>}
        <button className="ghost" onClick={() => onAsk(body)} disabled={!body.trim()} title="Continue in the assist panel">Ask</button>
      </div>

      {note && <div className="editor-note">{note}</div>}

      <textarea
        ref={area}
        className="editor-host"
        value={body}
        onChange={(e) => { setBody(e.target.value); }}
        spellCheck={false}
      />

      {readout && (
        <div className="editor-readout">
          <div className="row">
            <strong>Result</strong>
            <span className="spacer" />
            <button className="ghost" onClick={() => setReadout("")}>Dismiss</button>
          </div>
          <pre>{readout}</pre>
        </div>
      )}
    </aside>
  );
}
