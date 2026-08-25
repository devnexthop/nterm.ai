export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>) };
  if (init?.body && !(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { ...init, headers });
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
  return `${proto}://${location.host}/ws/term/${tabId}?session_id=${sessionId}`;
};
