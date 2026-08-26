// The backend requires a per-install token on every API and WebSocket call.
// It is injected into index.html at serve time; a cross-origin page cannot read
// that HTML (CORS is restricted), so it cannot obtain the token.
function readToken(): string {
  const meta = document.querySelector('meta[name="nterm-token"]');
  const fromMeta = meta?.getAttribute("content") || "";
  if (fromMeta) return fromMeta;
  // Vite dev server serves its own index.html, so fall back to an env token.
  return (import.meta as any).env?.VITE_NTERM_TOKEN || "";
}

export const NTERM_TOKEN = readToken();

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>) };
  if (init?.body && !(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (NTERM_TOKEN) headers["X-NTerm-Token"] = NTERM_TOKEN;

  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) {
    throw new Error(
      "NTerm rejected this request (401). The app token is missing or stale — reload the page."
    );
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      detail = await res.text();
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return (await res.text()) as T;
}

export const wsUrl = (tabId: string, sessionId: number) => {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const tok = NTERM_TOKEN ? `&token=${encodeURIComponent(NTERM_TOKEN)}` : "";
  return `${proto}://${location.host}/ws/term/${tabId}?session_id=${sessionId}${tok}`;
};
