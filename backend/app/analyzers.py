from __future__ import annotations

import re
from typing import Callable

Finding = dict


def _f(severity: str, title: str, detail: str, line: str = "") -> Finding:
    return {"severity": severity, "title": title, "detail": detail, "line": line}


def analyze_cisco(text: str) -> list[Finding]:
    findings = []
    low = text.lower()
    if re.search(r"^ip http server", text, re.M | re.I):
        findings.append(_f("high", "HTTP server enabled", "Disable with `no ip http server` unless required."))
    if re.search(r"transport input telnet", text, re.I):
        findings.append(_f("high", "Telnet allowed on VTY", "Prefer `transport input ssh`."))
    if re.search(r"snmp-server community public", text, re.I):
        findings.append(_f("high", "Default SNMP community `public`", "Use SNMPv3 or a unique RO/RW string."))
    if re.search(r"^enable secret", text, re.M | re.I) is None and "enable password" in low:
        findings.append(_f("medium", "Enable password not secret", "Use `enable secret`."))
    if re.search(r"^aaa new-model", text, re.M | re.I) is None:
        findings.append(_f("medium", "AAA not enabled", "Consider TACACS+/RADIUS with `aaa new-model`."))
    if re.search(r"^service password-encryption", text, re.M | re.I) is None:
        findings.append(_f("low", "Password encryption service off", "Add `service password-encryption`."))
    if re.search(r"^ntp server", text, re.M | re.I) is None:
        findings.append(_f("low", "No NTP server", "Time drift breaks logs and certs."))
    if re.search(r"^logging ", text, re.M | re.I) is None:
        findings.append(_f("medium", "No syslog destination", "Point `logging host` at NTerm syslog."))
    blocks = re.split(r"(?=^interface )", text, flags=re.M | re.I)
    for block in blocks:
        m = re.match(r"^interface (\S+)", block, re.I)
        if not m:
            continue
        iface = m.group(1)
        body = block.splitlines()
        if any(re.match(r"\s+shutdown\s*$", ln, re.I) for ln in body[1:]):
            findings.append(_f("info", f"Interface {iface} is shutdown", "Confirm this is intended.", iface))
    unused = re.findall(r"^interface (\S+)\s*$", text, re.M | re.I)
    if "line vty" in low and "login local" not in low and "login authentication" not in low:
        if re.search(r"^line vty[\s\S]*?^\s+login\s*$", text, re.M | re.I):
            findings.append(_f("high", "VTY uses simple `login`", "Move to local or AAA authentication."))
    if re.search(r"password cisco\b", text, re.I):
        findings.append(_f("critical", "Password is `cisco`", "Replace immediately."))
    if not findings:
        findings.append(_f("info", "No canned Cisco findings", "Paste a full `show running-config` for a deeper pass."))
    return findings


def analyze_pan(text: str) -> list[Finding]:
    findings = []
    if re.search(r"from any.*to any.*application any.*service any", text, re.I | re.S):
        findings.append(_f("critical", "Any/any security rule", "Restrict source, dest, app, and service."))
    if "admin" in text.lower() and "password" in text.lower():
        findings.append(_f("medium", "Admin credentials referenced in config", "Confirm not a default password."))
    if "profiles" not in text.lower():
        findings.append(_f("medium", "No security profiles spotted", "Attach AV/AS/VP/spyware profiles to allow rules."))
    if not findings:
        findings.append(_f("info", "No canned PAN-OS findings", "Export the running config XML or set CLI output."))
    return findings


def analyze_forti(text: str) -> list[Finding]:
    findings = []
    if re.search(r"set srcaddr ['\"]?all", text, re.I) and re.search(r"set dstaddr ['\"]?all", text, re.I):
        findings.append(_f("high", "Policy uses all/all", "Tighten address objects."))
    if re.search(r"set utm-status disable", text, re.I):
        findings.append(_f("medium", "UTM disabled on a policy", "Enable inspection where appropriate."))
    if "set password" in text.lower() and "fortinet" in text.lower():
        findings.append(_f("critical", "Possible default Fortinet password", "Rotate admin credentials."))
    if not findings:
        findings.append(_f("info", "No canned FortiOS findings", "Paste `show` output from the VDOM."))
    return findings


def analyze_generic(text: str) -> list[Finding]:
    findings = []
    if re.search(r"password\s+\S+", text, re.I):
        findings.append(_f("medium", "Cleartext password-like strings", "Review and rotate."))
    if "0.0.0.0/0" in text or "any any" in text.lower():
        findings.append(_f("medium", "Broad permit/any language", "Confirm blast radius."))
    if not findings:
        findings.append(_f("info", "Generic scan complete", "Choose a device-specific analyzer for deeper rules."))
    return findings


REGISTRY: dict[str, Callable[[str], list[Finding]]] = {
    "cisco_ios": analyze_cisco,
    "cisco_nxos": analyze_cisco,
    "cisco_asa": analyze_cisco,
    "paloalto": analyze_pan,
    "fortinet": analyze_forti,
    "generic": analyze_generic,
    "linux": analyze_generic,
}


def run_analyzers(device_type: str, text: str, extra: list[Callable] | None = None) -> list[Finding]:
    fn = REGISTRY.get(device_type, analyze_generic)
    out = fn(text)
    for extra_fn in extra or []:
        out.extend(extra_fn(text))
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    return sorted(out, key=lambda f: order.get(f["severity"], 9))
