export type DeviceType =
  | "generic"
  | "cisco_ios"
  | "cisco_nxos"
  | "cisco_asa"
  | "paloalto"
  | "fortinet"
  | "juniper"
  | "linux";

export type SessionKind = "ssh" | "telnet" | "serial" | "local" | "simulator";

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
  folder: string;
  credential_id: number | null;
  baud: number;
  created_at: string;
}

export interface Credential {
  id: number;
  name: string;
  username: string;
  device_type: string;
  notes: string;
  has_password: boolean;
  has_enable_password: boolean;
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
  /** False after Log off or a dropped socket — tab stays, session is not live. */
  live: boolean;
  /** Bump to force a reconnect without disposing the tab. */
  connNonce: number;
}

export interface AiModelOption {
  id: string;
  label: string;
}

export interface AiModelsResponse {
  provider: string;
  base_url: string;
  models: AiModelOption[];
  error?: string | null;
}

export interface Settings {
  openai_configured: boolean;
  openai_model: string;
  ai_provider: string;
  ai_base_url: string;
  anthropic_configured: boolean;
  ai_cache_enabled: boolean;
  theme: string;
  font_size: number;
  font_family: string;
  log_sessions: boolean;
  log_redact: boolean;
  ai_auto_context: boolean;
  bench_api_url: string;
  bench_mode: string;
  bench_key_configured: boolean;
  relay_configured: boolean;
  version?: string;
  build?: string;
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
  id?: string;
  name: string;
  command: string;
  extension?: string;
  editable?: boolean;
  device_types?: string[];
}

export interface SnippetPack {
  id: string;
  name: string;
}

export interface AiPreview {
  event_id: number;
  tool: string;
  args: Record<string, unknown>;
  commands: string[];
  summary: string;
  risk: string;
  dialect: string;
  cache_hit?: boolean;
  offline?: boolean;
  policy?: {
    verdict: "allow" | "warn" | "block";
    blocked: string[];
    warnings: string[];
    dialect: string;
  };
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
}

export interface AiEvent {
  id: number;
  created_at: string;
  customer_id: number | null;
  session_id: number | null;
  source: string;
  prompt: string;
  tool_name: string;
  commands_preview: string;
  decision: string;
  provider: string;
  model: string;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  cache_hit: boolean;
}

export interface TokenUsage {
  today: number;
  days_7: number;
  all: number;
  events: number;
}

export interface MenuItem {
  label: string;
  danger?: boolean;
  disabled?: boolean;
  run?: () => void;
}

export interface SerialPort {
  device: string;
  description: string;
}
