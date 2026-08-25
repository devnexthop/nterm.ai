export type DeviceType =
  | "generic"
  | "cisco_ios"
  | "cisco_nxos"
  | "cisco_asa"
  | "paloalto"
  | "fortinet"
  | "juniper"
  | "linux";

export type SessionKind = "ssh" | "local" | "simulator";

export interface SavedSession {
  id: number;
  customer_id: number;
  name: string;
  kind: SessionKind;
  device_type: DeviceType | string;
  host: string;
  port: number;
  username: string;
  has_password: boolean;
  has_enable_password: boolean;
  has_private_key: boolean;
  jump_host: string;
  notes: string;
  logging_enabled: boolean;
  post_login: string;
  created_at: string;
}

export interface Customer {
  id: number;
  name: string;
  color: string;
  notes: string;
  created_at: string;
  session_count: number;
  sessions: SavedSession[];
}

export interface OpenTab {
  tabId: string;
  session: SavedSession;
  customerName: string;
  selected: boolean;
}

export interface Settings {
  openai_configured: boolean;
  openai_model: string;
  theme: string;
  font_size: number;
  ai_auto_context: boolean;
  bench_api_url: string;
  bench_mode: string;
  bench_key_configured: boolean;
}

export interface Finding {
  severity: string;
  title: string;
  detail: string;
  line?: string;
}

export interface Extension {
  id: string;
  name: string;
  kind: string;
  enabled: boolean;
  builtin: boolean;
  description: string;
  manifest: Record<string, unknown>;
}

export interface McpServer {
  id: number;
  name: string;
  enabled: boolean;
  transport: string;
  url: string;
  command: string;
  args: string;
  notes: string;
}

export interface Snippet {
  name: string;
  command: string;
  extension?: string;
}
