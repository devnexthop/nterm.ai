"""Default-deny permit gate for drafted device configuration.

NTerm's promise is that nothing reaches a device the operator did not read.
That promise rests on a human, and a human reading amber text at 2am is a tired
check. This module is a second check sitting *below* the first one, and it does
not get tired: every drafted line has to match a shape we decided, in advance,
that a drafting model is allowed to produce.

Three rules, and they are the product:

1. Default deny. A line matching nothing in the dialect's permit list is
   "warn" — never "allow". The permit list is small on purpose. Growing it is a
   decision someone makes on the record, not something a clever prompt earns at
   runtime.
2. Deny wins. A deny shape blocks even when a permit shape also matched,
   because the dangerous drafts look exactly like legitimate config with one
   extra word in them.
3. Nothing is blocked silently. Every block and every warn carries a
   human-readable reason naming the shape that fired. A gate that quietly eats
   a line teaches operators to distrust the preview, which costs more safety
   than the gate buys.

This gate only ever *reduces* what reaches the human. There is no path here
that upgrades a verdict, and no caller-supplied way to add a permit — the same
reason shell.classify() forces destructive shapes to high risk regardless of
what the model claimed. The model is the thing we are guarding against.
"""
from __future__ import annotations

import re

ALLOW = "allow"
WARN = "warn"
BLOCK = "block"

DIALECTS = (
    "cisco_ios",
    "cisco_nxos",
    "cisco_iosxr",
    "juniper",
    "arista_eos",
    "paloalto",
    "fortinet",
)

# device_type strings arrive from saved sessions, so they are whatever an
# engineer typed years ago. Map the common spellings; anything unmapped stays
# unknown, which under default-deny means every line warns.
_ALIASES = {
    "ios": "cisco_ios", "ios_xe": "cisco_ios", "iosxe": "cisco_ios", "cisco": "cisco_ios",
    "cisco_ios_xe": "cisco_ios", "cisco_xe": "cisco_ios",
    "nxos": "cisco_nxos", "nx-os": "cisco_nxos", "nexus": "cisco_nxos", "cisco_nx_os": "cisco_nxos",
    "iosxr": "cisco_iosxr", "ios-xr": "cisco_iosxr", "xr": "cisco_iosxr", "cisco_ios_xr": "cisco_iosxr",
    "junos": "juniper", "juniper_junos": "juniper", "srx": "juniper", "mx": "juniper",
    "eos": "arista_eos", "arista": "arista_eos", "arista-eos": "arista_eos",
    "panos": "paloalto", "pan-os": "paloalto", "pan_os": "paloalto", "palo": "paloalto",
    "palo_alto": "paloalto", "paloalto_panos": "paloalto", "panorama": "paloalto",
    "fortios": "fortinet", "fortigate": "fortinet", "forti": "fortinet",
}
# Keys are normalized the same way the lookup input is, so "NX-OS", "nx-os" and
# "nx_os" all land on the same row instead of silently falling through to
# unknown — an alias that misses is a permit list that never applies.
_ALIASES = {k.replace("-", "_"): v for k, v in _ALIASES.items()}


def normalize_dialect(dialect: str | None) -> str:
    """Canonical dialect key. Unknown values are returned as-is and stay unknown."""
    d = (dialect or "").strip().lower().replace(" ", "_").replace("-", "_")
    if d in DIALECTS:
        return d
    return _ALIASES.get(d, d)


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.I)


# Any interface whose name says "out-of-band management". Losing this interface
# means losing the box, so config that darkens it is blocked rather than warned:
# the operator who would notice is the operator who just lost the session.
_MGMT = r"(?:mgmt[\w\-\.]*|management[\w\-\./]*|ma\d[\w/\.]*|fxp\d|em\d|me\d|vme\d|oob[\w\-]*)"
_MGMT_IFACE = _rx(r"^\"?" + _MGMT + r"\"?$")

# --------------------------------------------------------------------------
# DENY — global, and absolute. These are matched against every line of every
# dialect, because a model that emits IOS words into a Junos draft is exactly
# the failure this gate exists for. Order matters only for the reason text:
# the most specific shape in a category is listed first and wins the message.
# --------------------------------------------------------------------------
_DENY: list[tuple[str, str, re.Pattern]] = [
    # -- shell escape: the CLI stops being a CLI and becomes a computer -----
    ("shell-escape", "Tcl shell on the device", _rx(r"\btclsh\b")),
    ("shell-escape", "guest shell container", _rx(r"\bguestshell\b")),
    ("shell-escape", "Junos shell escape (start shell)", _rx(r"\bstart\s+shell\b")),
    ("shell-escape", "bash shell on the device", _rx(r"\b(run\s+bash|bash-shell|bash)\b")),
    ("shell-escape", "request-system shell access", _rx(r"\brequest\s+(system\s+)?shell\b")),
    ("shell-escape", "FortiOS raw system shell (fnsysctl)", _rx(r"\bfnsysctl\b")),
    ("shell-escape", "on-box scripting interpreter", _rx(r"\b(python|perl|guestshell\s+run)\b")),
    ("shell-escape", "EEM applet — runs arbitrary CLI later, unattended",
     _rx(r"\bevent\s+manager\s+(applet|policy)\b")),
    ("shell-escape", "pipe into a writer/interpreter", _rx(r"\|\s*(redirect|append|tee|tclsh|bash|save)\b")),
    ("shell-escape", "pivot to another host — leaves the audited session",
     _rx(r"^\s*(execute\s+)?(ssh|telnet)\s+\S")),
    ("shell-escape", "shell access", _rx(r"\bshell\b")),

    # -- destructive: unrecoverable without a console and a backup ----------
    ("destructive", "write erase — wipes startup config", _rx(r"\bwrite\s+erase\b")),
    ("destructive", "erase", _rx(r"\berase\b")),
    ("destructive", "filesystem format", _rx(r"^\s*format\b|\bformat\s+\S*(flash|disk|nvram|usb|slot|bootflash)")),
    ("destructive", "FortiOS log-disk format", _rx(r"\bformatlogdisk\b")),
    ("destructive", "forced/recursive file delete", _rx(r"\bdelete\s+/(force|recursive|f\b|r\b)")),
    ("destructive", "zeroize — destroys keys and config", _rx(r"\bzeroize\b")),
    ("destructive", "private-data-reset / factory reset",
     _rx(r"\b(private-data-reset|factory[\s\-]?reset|factorydefault|restore\s+factory)\b")),
    ("destructive", "purge — empties a whole configuration table", _rx(r"\bpurge\b")),

    # -- availability: the box survives, the service does not ---------------
    ("availability", "reload", _rx(r"\breload\b")),
    ("availability", "reboot", _rx(r"\breboot\b")),
    ("availability", "request system reboot/halt/power-off",
     _rx(r"\brequest\s+(system\s+)?(reboot|halt|power-off|powercycle)\b")),
    ("availability", "PAN-OS restart/shutdown of the system",
     _rx(r"\brequest\s+(restart|shutdown)\s+(system|software)\b")),
    ("availability", "execute reboot/shutdown", _rx(r"\bexecute\s+(reboot|shutdown)\b")),
    ("availability", "halt / power off", _rx(r"\b(poweroff|power-off|halt)\b")),

    # -- credentials and AAA: changing who can get in, or how ---------------
    ("credential", "local user with privilege 15",
     _rx(r"\busername\b.*\bprivilege\s+15\b")),
    ("credential", "creates or changes a local login",
     _rx(r"^\s*(no\s+)?username\s+\S+.*\b(secret|password|role|privilege)\b")),
    ("credential", "enable secret/password change", _rx(r"^\s*(no\s+)?enable\s+(secret|password)\b")),
    ("credential", "AAA configuration", _rx(r"^\s*(no\s+)?aaa\b")),
    # Anchored rather than blanket: a firewall policy may legitimately reference
    # a service object literally named RADIUS, and blocking that would be the
    # gate crying wolf. What we care about is a line that *configures* the
    # authentication server.
    ("credential", "TACACS+ server configuration",
     _rx(r"^\s*(no\s+)?tacacs[\w\-\+]*\b|^\s*(set|delete|config)\s+(system\s+|user\s+)?tacacs|\btacacs[\s\-]server\b|\bgroup\s+server\s+tacacs")),
    ("credential", "RADIUS server configuration",
     _rx(r"^\s*(no\s+)?radius[\w\-]*\b|^\s*(set|delete|config)\s+(system\s+|user\s+)?radius|\bradius[\s\-]server\b|\bgroup\s+server\s+radius")),
    ("credential", "Junos login/root authentication",
     _rx(r"^\s*(set|delete|deactivate)\s+system\s+(login|root-authentication|authentication-order)\b")),
    ("credential", "PAN-OS management user/role change",
     _rx(r"^\s*(set|delete)\s+mgt-config\s+(users|password-complexity)\b")),
    ("credential", "FortiOS admin account change", _rx(r"^\s*config\s+system\s+admin\b")),
    ("credential", "FortiOS external auth server change", _rx(r"^\s*config\s+user\s+(radius|tacacs|ldap|local)\b")),
    ("credential", "SNMP community string — a credential in clear text",
     _rx(r"\bsnmp-server\s+community\b")),

    # -- teardown: removing a whole protocol instance or the routing table --
    ("teardown", "disables IP routing entirely", _rx(r"^\s*no\s+ip\s+routing\b")),
    ("teardown", "disables IPv6 routing entirely", _rx(r"^\s*no\s+ipv6\s+unicast-routing\b")),
    ("teardown", "removes an entire routing-protocol instance",
     _rx(r"^\s*no\s+router\s+\w+")),
    ("teardown", "removes an entire NX-OS feature", _rx(r"^\s*no\s+feature\s+\S+")),
    ("teardown", "removes a whole Junos configuration hierarchy",
     _rx(r"^\s*(delete|deactivate)\s+(protocols|routing-options|routing-instances|system|security|interfaces|chassis)\s*$")),
    ("teardown", "removes an entire Junos protocol instance",
     _rx(r"^\s*(delete|deactivate)\s+protocols\s+[\w\-]+\s*$")),
    ("teardown", "removes the whole PAN-OS rulebase or virtual router",
     _rx(r"^\s*delete\s+(rulebase(\s+\w+)?(\s+rules)?|network\s+virtual-router\s+\S+)\s*$")),

    # -- lockout: still reachable in theory, not in practice ----------------
    ("lockout", "removes VTY access lines", _rx(r"^\s*no\s+line\s+vty\b")),
    ("lockout", "closes remote access to the CLI", _rx(r"\btransport\s+input\s+none\b")),
    ("lockout", "changes the management-plane address", _rx(r"^\s*set\s+deviceconfig\s+system\s+(ip-address|netmask|default-gateway|type)\b")),
    ("lockout", "removes the management service", _rx(r"^\s*(no\s+ip\s+ssh\b|delete\s+system\s+services\b)")),
    ("lockout", "disables the management interface",
     _rx(r"^\s*set\s+interfaces\s+" + _MGMT + r"\b.*\bdisable\b")),
    ("lockout", "removes the management interface",
     _rx(r"^\s*(delete|deactivate)\s+interfaces\s+" + _MGMT + r"\b")),
]

# Categories that a read-only line genuinely cannot trigger. `show aaa
# authentication` inspects AAA, it does not change it, and blocking the
# operator's ability to LOOK at the thing we are protecting is a gate that
# fights its own users. The categories left out of this set — shell escape,
# destructive, availability — stay absolute, because those act through a pipe
# or a hidden escape and do not care what verb the line started with.
_CHANGE_ONLY = {"credential", "teardown", "lockout"}

# A read-only verb. Used only to relax _CHANGE_ONLY deny rules — never to skip
# the permit check, and never to grant an allow on its own.
_READ_ONLY = _rx(
    r"^\s*(show|get|display|dir|ping|traceroute|trace|tracert|monitor|test|diagnose|"
    r"run\s+show)\b"
)

# --------------------------------------------------------------------------
# PERMIT — the small, boring set of shapes NTerm is in the business of
# drafting. Everything here is anchored at the start of the line: a permit that
# matches mid-line is a permit that can be prefixed with something else.
# --------------------------------------------------------------------------
_STRUCTURAL: list[tuple[str, str]] = [
    (r"^\s*$", "blank line"),
    (r"^\s*[!#].*$", "comment"),
    (r"^\s*(end|exit|top|up|quit|abort)\s*$", "leave a config context"),
    (r"^\s*(configure(\s+(terminal|private|exclusive))?|conf\s+t|config\s+t)\s*$", "enter config mode"),
    (r"^\s*commit(\s+(check|confirmed(\s+\d+)?|and-quit|force|description\s+.+|comment\s+.+))?\s*$", "commit the candidate config"),
    (r"^\s*(show|display|get)\s+\S.*$", "read-only show/get"),
    (r"^\s*(ping|traceroute|tracert)\s+\S.*$", "reachability test"),
]

_CISCO_SHARED: list[tuple[str, str]] = [
    (r"^\s*interface\s+[A-Za-z][\w\-/\.:]*\s*$", "select an interface"),
    (r"^\s*description\s+\S.*$", "interface/object description"),
    (r"^\s*no\s+shutdown\s*$", "bring an interface up"),
    (r"^\s*(speed|duplex|mtu|ip\s+mtu|bandwidth)\s+\S+\s*$", "interface media / MTU"),
    (r"^\s*switchport(\s+\S.*)?$", "switchport configuration"),
    (r"^\s*ip\s+helper-address\s+\d{1,3}(\.\d{1,3}){3}\s*$", "DHCP relay helper"),
    (r"^\s*vlan\s+\d+([,\-]\d+)*\s*$", "select a VLAN"),
    (r"^\s*name\s+[\w\-\.]+\s*$", "name a VLAN/object"),
    (r"^\s*ip\s+dhcp\s+pool\s+\S+\s*$", "DHCP pool"),
    (r"^\s*ip\s+dhcp\s+excluded-address\s+\d{1,3}(\.\d{1,3}){3}(\s+\d{1,3}(\.\d{1,3}){3})?\s*$", "DHCP exclusion"),
    (r"^\s*network\s+\d{1,3}(\.\d{1,3}){3}(\s+\d{1,3}(\.\d{1,3}){3}|/\d{1,2})?\s*$", "DHCP pool network"),
    (r"^\s*(default-router|dns-server)\s+\d{1,3}(\.\d{1,3}){3}(\s+\d{1,3}(\.\d{1,3}){3})*\s*$", "DHCP pool option"),
    (r"^\s*(domain-name\s+\S+|lease\s+[\d\s]+)\s*$", "DHCP pool option"),
    (r"^\s*ip(v6)?\s+access-list\s+(standard\s+|extended\s+)?\S+\s*$", "named ACL"),
    (r"^\s*access-list\s+\d+\s+(permit|deny)\s+\S.*$", "numbered ACL entry"),
    (r"^\s*(\d+\s+)?(permit|deny)\s+\S.*$", "ACL entry"),
    (r"^\s*remark\s+\S.*$", "ACL remark"),
    (r"^\s*ip(v6)?\s+access-group\s+\S+\s+(in|out)\s*$", "apply an ACL to an interface"),
    (r"^\s*ip\s+nat\s+(inside|outside)\s*$", "mark an interface for NAT"),
]

_IOS_ADDR = [
    (r"^\s*ip\s+address\s+\d{1,3}(\.\d{1,3}){3}\s+\d{1,3}(\.\d{1,3}){3}(\s+secondary)?\s*$", "IPv4 address on an interface"),
    (r"^\s*ipv6\s+address\s+[0-9A-Fa-f:]+/\d{1,3}\s*$", "IPv6 address on an interface"),
]

_IOS_ROUTE = [
    (r"^\s*ip\s+route\s+\d{1,3}(\.\d{1,3}){3}\s+\d{1,3}(\.\d{1,3}){3}\s+\S+(\s+\d+)?(\s+name\s+\S+)?\s*$", "IPv4 static route"),
    (r"^\s*ipv6\s+route\s+[0-9A-Fa-f:]+/\d{1,3}\s+\S+(\s+\d+)?\s*$", "IPv6 static route"),
]

_NXOS_ROUTE = [
    (r"^\s*ip\s+route\s+\d{1,3}(\.\d{1,3}){3}/\d{1,2}\s+\S+(\s+\S+)?\s*$", "IPv4 static route (prefix form)"),
    (r"^\s*ipv6\s+route\s+[0-9A-Fa-f:]+/\d{1,3}\s+\S+(\s+\S+)?\s*$", "IPv6 static route (prefix form)"),
]

_PERMITS: dict[str, list[tuple[str, str]]] = {
    "cisco_ios": _STRUCTURAL + _CISCO_SHARED + _IOS_ADDR + _IOS_ROUTE,
    "arista_eos": _STRUCTURAL + _CISCO_SHARED + _IOS_ADDR + _IOS_ROUTE + _NXOS_ROUTE,
    "cisco_nxos": _STRUCTURAL + _CISCO_SHARED + _IOS_ADDR + _IOS_ROUTE + _NXOS_ROUTE,
    "cisco_iosxr": _STRUCTURAL + _CISCO_SHARED + [
        (r"^\s*ipv4\s+address\s+\d{1,3}(\.\d{1,3}){3}\s+\d{1,3}(\.\d{1,3}){3}\s*$", "IPv4 address on an interface"),
        (r"^\s*ipv6\s+address\s+[0-9A-Fa-f:]+/\d{1,3}\s*$", "IPv6 address on an interface"),
        (r"^\s*router\s+static\s*$", "static routing container"),
        (r"^\s*address-family\s+ipv[46]\s+unicast\s*$", "static route address-family"),
        (r"^\s*\d{1,3}(\.\d{1,3}){3}/\d{1,2}\s+\S+\s*$", "static route entry"),
        (r"^\s*ipv[46]\s+access-list\s+\S+\s*$", "named ACL"),
    ],
    "juniper": _STRUCTURAL + [
        (r"^\s*set\s+interfaces\s+[\w\-/\.:]+(\s+unit\s+\d+)?\s+(description\s+\S.*|mtu\s+\d+|family\s+inet6?\s+(address\s+\S+|mtu\s+\d+)|vlan-id\s+\d+)\s*$", "interface address / description"),
        (r"^\s*set\s+routing-options\s+static\s+route\s+\S+\s+next-hop\s+\S+\s*$", "static route"),
        (r"^\s*set\s+routing-options\s+rib\s+\S+\s+static\s+route\s+\S+\s+next-hop\s+\S+\s*$", "static route in a RIB"),
        (r"^\s*set\s+firewall\s+\S.*$", "firewall filter / policer"),
        (r"^\s*set\s+security\s+(policies|zones|address-book|nat|application)\s+\S.*$", "SRX security policy / zone / NAT"),
        (r"^\s*set\s+applications\s+\S.*$", "application definition"),
        (r"^\s*set\s+policy-options\s+\S.*$", "routing policy object"),
        (r"^\s*edit\s+\S.*$", "enter a config hierarchy"),
        (r"^\s*run\s+show\s+\S.*$", "read-only show from config mode"),
        (r"^\s*rollback\s*0?\s*$", "discard the uncommitted candidate"),
    ],
    "paloalto": _STRUCTURAL + [
        (r"^\s*set\s+network\s+interface\s+\S.*$", "interface configuration"),
        (r"^\s*set\s+network\s+(zone|profiles|qos)\s+\S.*$", "zone / network profile"),
        (r"^\s*set\s+network\s+virtual-router\s+\S+\s+(routing-table|interface)\s+\S.*$", "static route / VR interface"),
        (r"^\s*set\s+rulebase\s+(security|nat|pbf)\s+rules\s+\S+\s+\S.*$", "security / NAT rule"),
        (r"^\s*set\s+(address|address-group|service|service-group|tag|application-group)\s+\S+\s+\S.*$", "policy object"),
        (r"^\s*set\s+vsys\s+\S+\s+(address|address-group|service|rulebase)\s+\S.*$", "vsys-scoped object or rule"),
        (r"^\s*test\s+\S.*$", "read-only policy/route test"),
    ],
    "fortinet": _STRUCTURAL + [
        (r"^\s*config\s+system\s+(interface|dhcp\s+server|zone)\s*$", "interface / DHCP / zone table"),
        (r"^\s*config\s+firewall\s+(policy|address|addrgrp|vip|vipgrp|ippool|service\s+custom|service\s+group|schedule\s+recurring)\s*$", "firewall table"),
        (r"^\s*config\s+router\s+static\s*$", "static route table"),
        (r"^\s*edit\s+\"?[\w\-\.\s/]+\"?\s*$", "select or create a table entry"),
        (r"^\s*next\s*$", "close a table entry"),
        (r"^\s*set\s+(ip|status|allowaccess|alias|description|comment|comments|role|type|interface|"
         r"associated-interface|vdom|mode|dst|gateway|device|distance|priority|blackhole|"
         r"extip|extintf|mappedip|mappedport|extport|portforward|protocol|"
         r"srcintf|dstintf|srcaddr|dstaddr|service|schedule|action|nat|logtraffic|name|"
         r"subnet|start-ip|end-ip|netmask|default-gateway|dns-service|domain|lease-time|"
         r"member|uuid|color|visibility)\s+\S.*$", "field on a permitted object"),
    ],
}

_COMPILED: dict[str, list[tuple[re.Pattern, str]]] = {
    d: [(_rx(p), shape) for p, shape in rules] for d, rules in _PERMITS.items()
}


def _clip(text: str, width: int = 100) -> str:
    t = text.strip()
    return t if len(t) <= width else t[: width - 1] + "…"


def _deny_hits(line: str) -> list[tuple[str, str]]:
    """(category, shape) for every deny rule that fires — one per category.

    One per category keeps the reason list readable: `write erase` matching both
    the specific shape and the generic `erase` shape is one problem, not two.
    Specific patterns are listed first so they win the message.
    """
    read_only = bool(_READ_ONLY.match(line))
    hits: list[tuple[str, str]] = []
    seen: set[str] = set()
    for category, shape, pattern in _DENY:
        if category in seen:
            continue
        if read_only and category in _CHANGE_ONLY:
            continue
        if pattern.search(line):
            hits.append((category, shape))
            seen.add(category)
    return hits


def _contextual_deny(line: str, iface: str | None) -> list[tuple[str, str]]:
    """Deny shapes that are only dangerous given the line above them.

    `shutdown` is harmless on a lab access port and is a site outage plus a
    truck roll on Management0/0. The permit list cannot see two lines at once,
    so the interface context is carried down the draft and checked here.
    """
    if not iface or not _MGMT_IFACE.match(iface):
        return []
    checks = (
        (r"^\s*shutdown\s*$", "shuts down the management interface"),
        (r"^\s*disable\s*$", "disables the management interface"),
        (r"^\s*set\s+status\s+down\s*$", "takes the management interface down"),
        (r"^\s*no\s+ip(v6)?\s+address\b", "removes the management address"),
        (r"^\s*unset\s+(ip|allowaccess)\b", "removes management access"),
    )
    for pattern, shape in checks:
        if re.match(pattern, line, re.I):
            return [("lockout", f"{shape} ({iface})")]
    return []


def evaluate(commands: list[str], dialect: str) -> tuple[str, list[str], list[str]]:
    """Judge a drafted command block.

    Returns (verdict, blocked_reasons, warnings):
      "block" — at least one line matched a deny shape. Do not offer Confirm.
      "warn"  — at least one line matched nothing in the permit list. Show it,
                loudly, and make the human own it.
      "allow" — every line matched a permit shape and nothing matched a deny
                shape. Still a draft. Still needs Confirm. "allow" here means
                "the gate has no objection", never "send it".
    """
    canon = normalize_dialect(dialect)
    permits = _COMPILED.get(canon)

    blocked: list[str] = []
    warnings: list[str] = []

    if permits is None:
        # An unknown dialect has no permit list, so every line falls through to
        # default-deny. That is the correct outcome, but say so once explicitly
        # rather than leaving the operator to infer it from N identical warns.
        warnings.append(
            f"unrecognized dialect {dialect!r} — no permit list for it, so every line "
            f"falls to default-deny"
        )
        permits = []

    # A model can smuggle a second command onto one list entry with a newline.
    # Split before matching so each real line faces the gate on its own.
    lines: list[str] = []
    for raw in commands or []:
        lines.extend(str(raw).replace("\r", "").split("\n"))

    if not lines:
        return WARN, [], warnings + ["empty draft — nothing to review, nothing to send"]

    iface: str | None = None
    for n, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip()
        shown = _clip(line)

        hits = _deny_hits(line) + _contextual_deny(line, iface)
        if hits:
            for category, shape in hits:
                blocked.append(f"line {n}: {shown!r} — DENY [{category}]: {shape}")
            # A denied line still updates context below; it is blocked, not
            # deleted, and the operator sees the whole draft.

        matched = next((shape for pattern, shape in permits if pattern.match(line)), None)
        if not matched and not hits:
            warnings.append(
                f"line {n}: {shown!r} — no permit shape for {canon}; default-deny, needs a human"
            )

        iface = _track_interface(line, iface)

    if blocked:
        return BLOCK, blocked, warnings
    if warnings:
        return WARN, [], warnings
    return ALLOW, [], []


def _track_interface(line: str, current: str | None) -> str | None:
    """Carry the 'which interface are we in' context down a draft."""
    m = re.match(r"^\s*interface\s+(\S+)", line, re.I)
    if m:
        return m.group(1)
    # FortiOS: `edit port1` inside `config system interface`. The table name is
    # not tracked because the only thing this context gates is mgmt-interface
    # shapes, and `set status down` on a non-interface table is a warn anyway.
    m = re.match(r"^\s*edit\s+\"?([\w\-\./]+)\"?\s*$", line, re.I)
    if m:
        return m.group(1)
    if re.match(r"^\s*(exit|end|next|top|configure|conf\s+t|config\s+t)\b|^\s*!", line, re.I):
        return None
    return current


def explain(dialect: str) -> dict:
    """Permit/deny summary for the UI, so a block can show its own reasoning.

    The operator seeing "blocked" deserves to see the rule, not a shrug — that
    is the difference between a safety feature and an obstacle.
    """
    canon = normalize_dialect(dialect)
    rules = _PERMITS.get(canon)
    deny_by_category: dict[str, list[dict]] = {}
    for category, shape, pattern in _DENY:
        deny_by_category.setdefault(category, []).append({"shape": shape, "pattern": pattern.pattern})
    return {
        "dialect": canon,
        "requested": dialect,
        "known": rules is not None,
        "default": "deny",
        "verdicts": {
            "allow": "every line matched a permit shape; still requires human Confirm",
            "warn": "at least one line matched no permit shape",
            "block": "at least one line matched a deny shape; deny always wins",
        },
        "permit": [{"shape": shape, "pattern": pattern} for pattern, shape in (rules or [])],
        "deny": deny_by_category,
        "deny_absolute": sorted(set(c for c, _, _ in _DENY) - _CHANGE_ONLY),
        "deny_change_only": sorted(_CHANGE_ONLY),
        "notes": [
            "Default deny: an unmatched line is 'warn', never 'allow'.",
            "A deny match always wins over a permit match.",
            "Read-only show/get lines are exempt from the change-only deny "
            "categories (credential, teardown, lockout) — looking is not changing.",
            "This gate only reduces what reaches the operator. It never auto-applies.",
        ],
    }


if __name__ == "__main__":
    # Sanity checks. Not a test framework — the same shape as shell.py's own
    # philosophy: the guard has to be runnable and provable on its own, because
    # the day it is wrong is the day nobody is looking.
    import sys

    _failures: list[str] = []
    _passes = 0

    def case(name: str, commands: list[str], dialect: str, want: str, mentions: str | None = None) -> None:
        global _passes
        verdict, blocked, warns = evaluate(commands, dialect)
        problems = []
        if verdict != want:
            problems.append(f"verdict {verdict!r}, wanted {want!r}")
        # Rule 3: nothing is ever blocked or warned silently.
        if want == BLOCK and not blocked:
            problems.append("blocked with no reason (silent block)")
        if want == WARN and not warns:
            problems.append("warned with no reason (silent warn)")
        if want == ALLOW and (blocked or warns):
            problems.append(f"allow carried reasons: {blocked + warns}")
        # Rule: a block never comes back as anything else.
        if blocked and verdict != BLOCK:
            problems.append("deny hits present but verdict is not block")
        if mentions and mentions.lower() not in " ".join(blocked + warns).lower():
            problems.append(f"reason never mentions {mentions!r}: {blocked + warns}")
        if problems:
            _failures.append(f"{name}: " + "; ".join(problems))
        else:
            _passes += 1

    # -- a normal permitted change, on every vendor ------------------------
    case("ios: interface address", [
        "configure terminal", "interface GigabitEthernet0/1",
        "ip address 10.0.0.1 255.255.255.0", "no shutdown", "end",
    ], "cisco_ios", ALLOW)
    case("ios: dhcp pool", [
        "configure terminal", "ip dhcp pool LAB", "network 10.10.10.0 255.255.255.0",
        "default-router 10.10.10.1", "dns-server 10.10.10.1", "end",
    ], "cisco_ios", ALLOW)
    case("ios: static route", [
        "configure terminal", "ip route 10.0.0.0 255.0.0.0 192.168.1.1", "end",
    ], "cisco_ios", ALLOW)
    case("ios: acl entries", [
        "configure terminal", "ip access-list extended NTERM-IN",
        "permit tcp any host 10.0.0.5 eq 443", "deny ip any any log", "end",
    ], "cisco_ios", ALLOW)
    case("nxos: interface + prefix route", [
        "configure terminal", "interface Ethernet1/5",
        "ip address 10.1.1.1 255.255.255.0", "no shutdown",
        "ip route 10.0.0.0/8 10.1.1.2", "end",
    ], "cisco_nxos", ALLOW)
    case("iosxr: interface + static route", [
        "configure terminal", "interface GigabitEthernet0/0/0/1",
        "ipv4 address 10.2.2.1 255.255.255.0", "no shutdown",
        "router static", "address-family ipv4 unicast", "10.9.0.0/16 10.2.2.254",
        "commit", "end",
    ], "cisco_iosxr", ALLOW)
    case("juniper: address + static route", [
        "configure",
        "set interfaces ge-0/0/1 unit 0 family inet address 10.3.3.1/24",
        "set routing-options static route 10.9.0.0/16 next-hop 10.3.3.254",
        "set security policies from-zone trust to-zone untrust policy nterm-allow then permit",
        "commit",
    ], "juniper", ALLOW)
    case("arista: interface address", [
        "configure terminal", "interface Ethernet3",
        "ip address 10.4.4.1 255.255.255.0", "no shutdown", "end",
    ], "arista_eos", ALLOW)
    case("paloalto: security rule (adapters._palo output)", [
        "configure",
        "set rulebase security rules nterm-allow from any",
        "set rulebase security rules nterm-allow to any",
        "set rulebase security rules nterm-allow source 10.0.0.0/24",
        "set rulebase security rules nterm-allow destination any",
        "set rulebase security rules nterm-allow application dns",
        "set rulebase security rules nterm-allow service application-default",
        "set rulebase security rules nterm-allow action allow",
        "commit",
    ], "paloalto", ALLOW)
    case("paloalto: static route (adapters._route output)", [
        "configure",
        "set network virtual-router default routing-table ip static-route nterm-r "
        "destination 10.0.0.0/8 nexthop ip-address 10.1.1.1",
        "commit",
    ], "paloalto", ALLOW)
    case("fortinet: VIP (adapters._vip output)", [
        "config firewall vip", "edit web-ext", "set extip 1.2.3.4", "set extintf any",
        "set mappedip 10.0.0.5", "set portforward enable", "set protocol tcp",
        "set extport 443", "set mappedport 443", "next", "end",
    ], "fortinet", ALLOW)
    case("fortinet: interface address", [
        "config system interface", "edit port2", "set ip 10.5.5.1 255.255.255.0",
        "set status up", "next", "end",
    ], "fortinet", ALLOW)
    case("fortinet: static route", [
        "config router static", "edit 0", "set dst 10.0.0.0/8",
        "set gateway 10.5.5.254", "next", "end",
    ], "fortinet", ALLOW)

    # -- show commands, on every vendor ------------------------------------
    for _d, _cmd in (
        ("cisco_ios", "show ip interface brief"),
        ("cisco_nxos", "show interface status"),
        ("cisco_iosxr", "show ipv4 interface brief"),
        ("juniper", "show interfaces terse"),
        ("arista_eos", "show ip interface brief"),
        ("paloalto", "show interface all"),
        ("fortinet", "get system interface"),
    ):
        case(f"{_d}: read-only show", [_cmd], _d, ALLOW)

    # Looking at AAA is not changing AAA. The change-only deny categories must
    # not fire on a read-only verb, or the gate blocks the operator's ability
    # to inspect the very thing it protects.
    case("ios: show aaa is not an aaa change", ["show aaa authentication"], "cisco_ios", ALLOW)

    # -- shell escapes, on every vendor ------------------------------------
    case("ios: tclsh", ["configure terminal", "tclsh"], "cisco_ios", BLOCK, "Tcl")
    case("ios: guestshell", ["guestshell run bash"], "cisco_ios", BLOCK, "shell")
    case("nxos: run bash", ["run bash"], "cisco_nxos", BLOCK, "bash")
    case("juniper: start shell", ["start shell user root"], "juniper", BLOCK, "shell")
    case("juniper: request system shell", ["request system shell"], "juniper", BLOCK, "shell")
    case("iosxr: run bash", ["run bash"], "cisco_iosxr", BLOCK, "bash")
    case("arista: bash escape", ["bash sudo su -"], "arista_eos", BLOCK, "bash")
    case("fortinet: fnsysctl", ["fnsysctl ls /"], "fortinet", BLOCK, "fnsysctl")
    case("paloalto: pivot out of the audited session",
         ["ssh host 10.0.0.9"], "paloalto", BLOCK, "pivot")
    case("ios: pipe into a writer", ["show running-config | redirect ftp://10.0.0.9/cfg"],
         "cisco_ios", BLOCK, "pipe")
    case("ios: pipe into an interpreter", ["show running-config | tclsh"],
         "cisco_ios", BLOCK, "Tcl")
    case("ios: EEM applet is a delayed shell",
         ["event manager applet PWN", "action 1.0 cli command \"write erase\""],
         "cisco_ios", BLOCK, "EEM")

    # -- destructive -------------------------------------------------------
    case("ios: write erase", ["write erase"], "cisco_ios", BLOCK, "write erase")
    case("ios: erase startup-config", ["erase startup-config"], "cisco_ios", BLOCK, "erase")
    case("ios: format flash", ["format flash:"], "cisco_ios", BLOCK, "format")
    case("ios: delete /force", ["delete /force /recursive flash:"], "cisco_ios", BLOCK, "delete")
    case("juniper: zeroize", ["request system zeroize"], "juniper", BLOCK, "zeroize")
    case("paloalto: private-data-reset",
         ["request system private-data-reset"], "paloalto", BLOCK, "reset")
    case("fortinet: factoryreset", ["execute factoryreset"], "fortinet", BLOCK, "factory")
    case("fortinet: purge a table",
         ["config firewall policy", "purge"], "fortinet", BLOCK, "purge")

    # -- availability ------------------------------------------------------
    case("ios: reload", ["reload"], "cisco_ios", BLOCK, "reload")
    case("nxos: reload after config", [
        "configure terminal", "interface Ethernet1/5", "no shutdown", "end", "reload",
    ], "cisco_nxos", BLOCK, "reload")
    case("juniper: request system reboot", ["request system reboot"], "juniper", BLOCK, "reboot")
    case("paloalto: request restart system", ["request restart system"], "paloalto", BLOCK, "restart")
    case("fortinet: execute reboot", ["execute reboot"], "fortinet", BLOCK, "reboot")
    case("ios: shutdown on the management interface", [
        "configure terminal", "interface Management0/0", "shutdown", "end",
    ], "cisco_ios", BLOCK, "management")
    case("ios: shutdown on a data port is only a warn (not permitted, not denied)", [
        "configure terminal", "interface GigabitEthernet0/3", "shutdown", "end",
    ], "cisco_ios", WARN)
    case("ios: no shutdown on mgmt is fine", [
        "configure terminal", "interface Management0/0", "no shutdown", "end",
    ], "cisco_ios", ALLOW)
    case("juniper: disable fxp0", [
        "set interfaces fxp0 unit 0 disable",
    ], "juniper", BLOCK, "management")
    case("fortinet: mgmt interface down", [
        "config system interface", "edit mgmt", "set status down", "next", "end",
    ], "fortinet", BLOCK, "management")

    # -- credentials / AAA -------------------------------------------------
    case("ios: username privilege 15",
         ["username backdoor privilege 15 secret Passw0rd"], "cisco_ios", BLOCK, "privilege 15")
    case("ios: aaa new-model", ["aaa new-model"], "cisco_ios", BLOCK, "AAA")
    case("ios: tacacs server", ["tacacs-server host 10.9.9.9 key sekret"], "cisco_ios", BLOCK, "TACACS")
    case("ios: radius server", ["radius-server host 10.9.9.9"], "cisco_ios", BLOCK, "RADIUS")
    case("ios: snmp community", ["snmp-server community public RW"], "cisco_ios", BLOCK, "SNMP")
    case("juniper: login class change",
         ["set system login user backdoor class super-user"], "juniper", BLOCK, "login")
    case("paloalto: mgt-config user",
         ["set mgt-config users backdoor permissions role-based superuser yes"],
         "paloalto", BLOCK, "management user")
    case("fortinet: admin account",
         ["config system admin", "edit backdoor", "set password x", "next", "end"],
         "fortinet", BLOCK, "admin")
    case("fortinet: a service object named RADIUS is not a RADIUS change", [
        "config firewall policy", "edit 0", "set service RADIUS", "next", "end",
    ], "fortinet", ALLOW)

    # -- teardown ----------------------------------------------------------
    case("ios: no ip routing", ["no ip routing"], "cisco_ios", BLOCK, "routing")
    case("ios: no router bgp", ["no router bgp 65000"], "cisco_ios", BLOCK, "protocol instance")
    case("nxos: no feature", ["no feature bgp"], "cisco_nxos", BLOCK, "feature")
    case("juniper: delete protocols bgp", ["delete protocols bgp"], "juniper", BLOCK, "protocol instance")
    case("juniper: delete the whole system hierarchy", ["delete system"], "juniper", BLOCK, "hierarchy")
    case("paloalto: delete the whole rulebase",
         ["delete rulebase security rules"], "paloalto", BLOCK, "rulebase")

    # -- default deny ------------------------------------------------------
    case("ios: unknown command warns, never allows",
         ["configure terminal", "ntp server 1.1.1.1", "end"], "cisco_ios", WARN, "default-deny")
    case("ios: banner is not on the permit list",
         ["banner motd ^C maintenance ^C"], "cisco_ios", WARN, "default-deny")
    case("fortinet: unpermitted global config warns",
         ["config system global", "set hostname edge1", "end"], "fortinet", WARN, "default-deny")
    case("unknown dialect: everything falls to default-deny",
         ["ip addr add 10.0.0.1/24 dev eth0"], "linux", WARN, "unrecognized dialect")
    case("empty draft", [], "cisco_ios", WARN, "empty draft")

    # -- deny beats permit, and cannot be hidden ---------------------------
    case("deny wins over a permitted block", [
        "configure terminal", "interface GigabitEthernet0/1",
        "ip address 10.0.0.1 255.255.255.0", "no shutdown", "write erase", "end",
    ], "cisco_ios", BLOCK, "write erase")
    case("newline smuggling on one list entry", [
        "configure terminal\nwrite erase",
    ], "cisco_ios", BLOCK, "write erase")
    case("dialect aliases resolve", [
        "configure terminal", "interface Ethernet1/5",
        "ip address 10.1.1.1 255.255.255.0", "no shutdown", "end",
    ], "NX-OS", ALLOW)

    # -- explain() tells the UI why ----------------------------------------
    for _d in DIALECTS:
        _x = explain(_d)
        if not _x["known"] or not _x["permit"] or not _x["deny"] or _x["default"] != "deny":
            _failures.append(f"explain({_d}): incomplete summary")
        else:
            _passes += 1
    _x = explain("linux")
    if _x["known"] or _x["permit"] or not _x["deny"]:
        _failures.append("explain(linux): unknown dialect must still expose the deny list")
    else:
        _passes += 1

    print(f"policy gate sanity: {_passes} passed, {len(_failures)} failed")
    for f in _failures:
        print("  FAIL", f)
    sys.exit(1 if _failures else 0)
