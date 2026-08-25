from datetime import datetime
from pydantic import BaseModel, Field


class CustomerIn(BaseModel):
    name: str
    color: str = "#ffb020"
    notes: str = ""


class CustomerOut(CustomerIn):
    id: int
    created_at: datetime
    session_count: int = 0


class SessionIn(BaseModel):
    customer_id: int
    name: str
    kind: str = "ssh"
    device_type: str = "generic"
    host: str = ""
    port: int = 22
    username: str = ""
    password: str | None = None
    enable_password: str | None = None
    private_key: str | None = None
    jump_host: str = ""
    notes: str = ""
    logging_enabled: bool = True
    post_login: str = ""


class SessionOut(BaseModel):
    id: int
    customer_id: int
    name: str
    kind: str
    device_type: str
    host: str
    port: int
    username: str
    has_password: bool
    has_enable_password: bool
    has_private_key: bool
    jump_host: str
    notes: str
    logging_enabled: bool
    post_login: str
    created_at: datetime


class SessionUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    device_type: str | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    enable_password: str | None = None
    private_key: str | None = None
    jump_host: str | None = None
    notes: str | None = None
    logging_enabled: bool | None = None
    post_login: str | None = None
    customer_id: int | None = None


class SettingsOut(BaseModel):
    openai_configured: bool
    openai_model: str
    theme: str
    font_size: int
    ai_auto_context: bool
    bench_api_url: str
    bench_mode: str
    bench_key_configured: bool


class SettingsIn(BaseModel):
    openai_api_key: str | None = None
    openai_model: str | None = None
    theme: str | None = None
    font_size: int | None = None
    ai_auto_context: bool | None = None
    bench_api_url: str | None = None
    bench_mode: str | None = None
    bench_api_key: str | None = None


class McpIn(BaseModel):
    name: str
    enabled: bool = True
    transport: str = "sse"
    url: str = ""
    command: str = ""
    args: str = ""
    notes: str = ""


class McpOut(McpIn):
    id: int


class AnalyzeRequest(BaseModel):
    device_type: str = "cisco_ios"
    text: str = ""
    log_id: int | None = None
    session_id: int | None = None
    analyzer_ids: list[str] = Field(default_factory=list)


class AiChatIn(BaseModel):
    message: str
    session_id: int | None = None
    transcript: str = ""
    device_type: str = "generic"
    customer_name: str = ""
    allow_tools: bool = True


class BroadcastIn(BaseModel):
    tab_ids: list[str]
    command: str
    newline: bool = True


class ExtensionToggle(BaseModel):
    enabled: bool


class ExtensionInstall(BaseModel):
    manifest: dict


class ToolkitServiceIn(BaseModel):
    enabled: bool | None = None
    bind: str | None = None
    port: int | None = None
    config: dict | None = None


class SubnetIn(BaseModel):
    cidr: str
    split: int | None = None


class Type7In(BaseModel):
    text: str
    mode: str = "decode"
    seed: int = 15


class DiffIn(BaseModel):
    before: str
    after: str


class AclIn(BaseModel):
    cidr: str
    proto: str = "ip"
    dest: str = "any"
    action: str = "permit"


class SummarizeIn(BaseModel):
    cidrs: str


class TranslateIn(BaseModel):
    line: str
    target: str = "paloalto"
