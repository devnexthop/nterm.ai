import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import type { OpenTab } from "../types";
import { wsUrl } from "../api";
import type { ChromeTheme } from "../themes";

const sockets = new Map<string, WebSocket>();
const buffers = new Map<string, string>();

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
  active,
}: {
  tab: OpenTab;
  theme: ChromeTheme;
  fontSize: number;
  active: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);

  useEffect(() => {
    if (!host.current) return;
    const term = new Terminal({
      cursorBlink: true,
      fontFamily: '"IBM Plex Mono", ui-monospace, monospace',
      fontSize,
      theme: theme.term,
      scrollback: 8000,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.loadAddon(new WebLinksAddon());
    term.open(host.current);
    fit.fit();
    termRef.current = term;

    const ws = new WebSocket(wsUrl(tab.tabId, tab.session.id));
    sockets.set(tab.tabId, ws);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "output") {
        term.write(msg.data);
        const prev = buffers.get(tab.tabId) || "";
        buffers.set(tab.tabId, (prev + msg.data).slice(-20000));
      } else if (msg.type === "status") {
        term.write(`\r\n\x1b[90m[${msg.state}${msg.message ? " · " + msg.message : ""}]\x1b[0m\r\n`);
      }
    };
    ws.onclose = () => {
      term.write("\r\n\x1b[90m[disconnected]\x1b[0m\r\n");
    };
    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }));
      }
    });
    const ro = new ResizeObserver(() => {
      fit.fit();
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      }
    });
    ro.observe(host.current);
    return () => {
      ro.disconnect();
      ws.close();
      sockets.delete(tab.tabId);
      term.dispose();
    };
  }, [tab.tabId, tab.session.id]);

  useEffect(() => {
    termRef.current?.options && (termRef.current.options.theme = theme.term);
    if (termRef.current) termRef.current.options.fontSize = fontSize;
  }, [theme, fontSize]);

  useEffect(() => {
    if (active) termRef.current?.focus();
  }, [active]);

  return <div className="term-host" ref={host} />;
}
