import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import type { MenuItem, OpenTab } from "../types";
import { wsUrl } from "../api";
import type { ChromeTheme } from "../themes";
import ContextMenu from "./ContextMenu";

const sockets = new Map<string, WebSocket>();
const buffers = new Map<string, string>();
const terms = new Map<string, Terminal>();

export function getBuffer(tabId: string) {
  return buffers.get(tabId) || "";
}

export function sendToTab(tabId: string, data: string) {
  sockets.get(tabId)?.send(JSON.stringify({ type: "input", data }));
}

export default function TerminalPane({
  tab,
  theme,
  fontSize,
  fontFamily,
  active,
  onEditText,
  onAskAi,
  onDead,
}: {
  tab: OpenTab;
  theme: ChromeTheme;
  fontSize: number;
  fontFamily?: string;
  active: boolean;
  onEditText?: (text: string, title: string) => void;
  onAskAi?: (text: string) => void;
  onDead?: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [menu, setMenu] = useState<{ x: number; y: number; items: MenuItem[] } | null>(null);

  useEffect(() => {
    if (!host.current) return;
    const term = new Terminal({
      cursorBlink: true,
      fontFamily: `${JSON.stringify(fontFamily || "IBM Plex Mono")}, ui-monospace, monospace`,
      fontSize,
      theme: theme.term,
      scrollback: 8000,
      rightClickSelectsWord: false,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.loadAddon(new WebLinksAddon());
    term.open(host.current);
    fit.fit();
    termRef.current = term;
    terms.set(tab.tabId, term);

    term.onData((data) => {
      const ws = wsRef.current;
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }));
      }
    });
    const ro = new ResizeObserver(() => {
      fit.fit();
      const ws = wsRef.current;
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      }
    });
    ro.observe(host.current);
    return () => {
      ro.disconnect();
      sockets.delete(tab.tabId);
      terms.delete(tab.tabId);
      term.dispose();
      termRef.current = null;
    };
  }, [tab.tabId, tab.session.id]);

  useEffect(() => {
    const term = termRef.current;
    if (!tab.live) {
      term?.write("\r\n\x1b[90m[logged off]\x1b[0m\r\n");
      return;
    }
    let planned = false;
    const ws = new WebSocket(wsUrl(tab.tabId, tab.session.id));
    wsRef.current = ws;
    sockets.set(tab.tabId, ws);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "output") {
        termRef.current?.write(msg.data);
        const prev = buffers.get(tab.tabId) || "";
        buffers.set(tab.tabId, (prev + msg.data).slice(-20000));
      } else if (msg.type === "status") {
        termRef.current?.write(
          `\r\n\x1b[90m[${msg.state}${msg.message ? " · " + msg.message : ""}]\x1b[0m\r\n`,
        );
      }
    };
    ws.onclose = () => {
      if (wsRef.current === ws) {
        wsRef.current = null;
        sockets.delete(tab.tabId);
      }
      if (!planned) {
        termRef.current?.write("\r\n\x1b[90m[disconnected]\x1b[0m\r\n");
        onDead?.();
      }
    };
    return () => {
      planned = true;
      ws.onclose = null;
      ws.close();
      if (wsRef.current === ws) {
        wsRef.current = null;
        sockets.delete(tab.tabId);
      }
    };
  }, [tab.tabId, tab.session.id, tab.live, tab.connNonce]);

  useEffect(() => {
    termRef.current?.options && (termRef.current.options.theme = theme.term);
    if (termRef.current) {
      termRef.current.options.fontSize = fontSize;
      termRef.current.options.fontFamily =
        `${JSON.stringify(fontFamily || "IBM Plex Mono")}, ui-monospace, monospace`;
    }
  }, [theme, fontSize, fontFamily]);

  useEffect(() => {
    if (active) termRef.current?.focus();
  }, [active]);

  function openMenu(e: MouseEvent) {
    e.preventDefault();
    const term = termRef.current;
    const selected = term?.getSelection() || "";
    const items: MenuItem[] = [
      {
        label: "Copy",
        disabled: !selected,
        run: () => selected && navigator.clipboard.writeText(selected),
      },
      {
        label: "Paste",
        run: async () => {
          try {
            const text = await navigator.clipboard.readText();
            if (text) sendToTab(tab.tabId, text);
          } catch {
            /* clipboard denied */
          }
        },
      },
      {
        label: "Select all",
        run: () => term?.selectAll(),
      },
      { label: "—" },
      {
        label: "Edit in editor",
        disabled: !selected,
        run: () => onEditText?.(selected, `${tab.session.name} selection`),
      },
      {
        label: "Ask AI: what is this?",
        disabled: !selected,
        run: () => onAskAi?.(`What is this output?\n\n${selected}`),
      },
      {
        label: "Ask AI: explain / next step",
        disabled: !selected,
        run: () => onAskAi?.(`Explain this and tell me the next command if something is wrong.\n\n${selected}`),
      },
      {
        label: "Open buffer in editor",
        run: () => onEditText?.(getBuffer(tab.tabId), `${tab.session.name} buffer`),
      },
      {
        label: "Save selection as file",
        disabled: !selected,
        run: () => {
          const blob = new Blob([selected], { type: "text/plain" });
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = `${tab.session.name}.txt`;
          a.click();
        },
      },
    ];
    setMenu({ x: e.clientX, y: e.clientY, items });
  }

  return (
    <>
      <div className="term-host" ref={host} onContextMenu={openMenu} />
      {menu && <ContextMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => setMenu(null)} />}
    </>
  );
}
