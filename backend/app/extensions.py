from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Extension

BUILTIN = [
    {
        "id": "svc-syslog",
        "name": "Syslog server",
        "kind": "service",
        "enabled": True,
        "description": "Kiwi-style receiver. Point devices at NTerm and watch events live.",
        "manifest": {"service": "syslog", "default_port": 514},
    },
    {
        "id": "svc-tftp",
        "name": "TFTP server",
        "kind": "service",
        "enabled": True,
        "description": "TFTPD32-style file service for `copy tftp flash` and config backup.",
        "manifest": {"service": "tftp", "default_port": 69},
    },
    {
        "id": "svc-dhcp",
        "name": "DHCP server",
        "kind": "service",
        "enabled": True,
        "description": "Lab / ZTP scopes with option 66/67/150 for phone and switch provisioning.",
        "manifest": {"service": "dhcp", "default_port": 67},
    },
    {
        "id": "svc-calculator",
        "name": "Subnet calculator",
        "kind": "tool",
        "enabled": True,
        "description": "CIDR, wildcard masks, and VLSM split — architect scratchpad.",
        "manifest": {"tool": "subnet"},
    },
    {
        "id": "cisco-essentials",
        "name": "Cisco essentials",
        "kind": "snippets",
        "enabled": True,
        "description": "One-click show commands and hardening snippets for IOS/XE/NX-OS.",
        "manifest": {
            "device_types": ["cisco_ios", "cisco_nxos", "cisco_asa"],
            "snippets": [
                {"name": "Int brief", "command": "show ip interface brief"},
                {"name": "CDP neighbors", "command": "show cdp neighbors"},
                {"name": "Routes", "command": "show ip route"},
                {"name": "Running-config", "command": "show running-config"},
                {"name": "Disable paging", "command": "terminal length 0"},
                {"name": "Save", "command": "write memory"},
            ],
        },
    },
    {
        "id": "palo-essentials",
        "name": "PAN-OS essentials",
        "kind": "snippets",
        "enabled": True,
        "description": "Operational commands for Palo Alto firewalls.",
        "manifest": {
            "device_types": ["paloalto"],
            "snippets": [
                {"name": "System info", "command": "show system info"},
                {"name": "Interfaces", "command": "show interface all"},
                {"name": "Routes", "command": "show routing route"},
                {"name": "Jobs", "command": "show jobs all"},
                {"name": "Pager off", "command": "set cli pager off"},
            ],
        },
    },
    {
        "id": "forti-essentials",
        "name": "FortiOS essentials",
        "kind": "snippets",
        "enabled": True,
        "description": "Status and interface snippets for FortiGate.",
        "manifest": {
            "device_types": ["fortinet"],
            "snippets": [
                {"name": "System status", "command": "get system status"},
                {"name": "Interfaces", "command": "get system interface"},
                {"name": "Routes", "command": "get router info routing-table all"},
                {"name": "Standard output", "command": "config system console\nset output standard\nend"},
            ],
        },
    },
    {
        "id": "cisco-config-audit",
        "name": "Cisco config analyzer",
        "kind": "analyzer",
        "enabled": True,
        "description": "Flags HTTP, Telnet, default SNMP, missing AAA, and weak VTY login.",
        "manifest": {"analyzer": "cisco_ios"},
    },
    {
        "id": "pan-config-audit",
        "name": "PAN-OS config analyzer",
        "kind": "analyzer",
        "enabled": True,
        "description": "Looks for any/any rules and missing security profiles.",
        "manifest": {"analyzer": "paloalto"},
    },
    {
        "id": "forti-config-audit",
        "name": "FortiOS config analyzer",
        "kind": "analyzer",
        "enabled": True,
        "description": "Looks for all/all policies and disabled UTM.",
        "manifest": {"analyzer": "fortinet"},
    },
    {
        "id": "theme-pack",
        "name": "Theme pack",
        "kind": "theme",
        "enabled": True,
        "description": "NTerm Dark, Warp Midnight, CRT Amber, PuTTY, Nord, Solarized, High Contrast.",
        "manifest": {
            "themes": [
                "relay",
                "warp",
                "crt_amber",
                "putty",
                "nord",
                "solarized",
                "high_contrast",
            ]
        },
    },
]


def sync_builtin(db: Session) -> None:
    for spec in BUILTIN:
        row = db.get(Extension, spec["id"])
        if row:
            row.name = spec["name"]
            row.kind = spec["kind"]
            row.description = spec["description"]
            row.manifest = spec["manifest"]
            row.builtin = True
        else:
            db.add(Extension(**spec, builtin=True))
    db.commit()


def enabled_snippets(db: Session, device_type: str | None = None) -> list[dict]:
    out = []
    for ext in db.query(Extension).filter(Extension.enabled.is_(True), Extension.kind == "snippets"):
        types = ext.manifest.get("device_types") or []
        if device_type and types and device_type not in types:
            continue
        for snip in ext.manifest.get("snippets", []):
            out.append({**snip, "extension": ext.id})
    return out
