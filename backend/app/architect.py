"""CCNA / CCNP / CCIE workbench — offline, no lab required."""

from __future__ import annotations

import difflib
import ipaddress
import re
from typing import Iterable

# Cisco IOS type-7 Vigenère table (public, used by every CCIE)
_XLATE = b"dsfd;kfoA,.iyewrkldJKDHSUBsgvca69834ncxv9873254k"


def type7_decode(cipher: str) -> str:
    raw = re.sub(r"[^0-9A-Fa-f]", "", cipher)
    if len(raw) < 4 or len(raw) % 2:
        raise ValueError("Not a Cisco type-7 string")
    seed = int(raw[:2])
    out = []
    for i in range(2, len(raw), 2):
        val = int(raw[i : i + 2], 16)
        out.append(chr(val ^ _XLATE[(seed + (i - 2) // 2) % len(_XLATE)]))
    return "".join(out)


def type7_encode(plain: str, seed: int = 15) -> str:
    if not 0 <= seed <= 15:
        seed = 15
    parts = [f"{seed:02d}"]
    for i, ch in enumerate(plain):
        parts.append(f"{ord(ch) ^ _XLATE[(seed + i) % len(_XLATE)]:02X}")
    return "".join(parts)


def summarize(cidrs: Iterable[str]) -> dict:
    nets = [ipaddress.ip_network(c.strip(), strict=False) for c in cidrs if c.strip()]
    if not nets:
        raise ValueError("Paste one CIDR per line")
    collapsed = list(ipaddress.collapse_addresses(nets))
    return {
        "input_count": len(nets),
        "summaries": [
            {
                "cidr": str(n),
                "network": str(n.network_address),
                "netmask": str(n.netmask) if n.version == 4 else None,
                "wildcard": str(n.hostmask) if n.version == 4 else None,
                "prefix": n.prefixlen,
            }
            for n in collapsed
        ],
    }


def acl_lines(cidr: str, proto: str = "ip", dest: str = "any", action: str = "permit") -> dict:
    net = ipaddress.ip_network(cidr, strict=False)
    if net.version != 4:
        raise ValueError("Classic IOS ACLs want IPv4. Use an IPv6 prefix-list for v6.")
    src = f"{net.network_address} {net.hostmask}"
    ios = f"{action} {proto} {src} {dest}"
    nxos = f"{action} {proto} {net.with_prefixlen} {dest}"
    return {
        "ios_extended": ios,
        "ios_standard": f"{action} {src}",
        "nxos": nxos,
        "prefix_list": f"ip prefix-list NTERM seq 10 {action} {net.with_prefixlen}",
        "wildcard": str(net.hostmask),
        "inverse_mask_note": "IOS uses wildcard (inverse) masks, not subnet masks.",
    }


def config_diff(before: str, after: str) -> dict:
    a = before.splitlines()
    b = after.splitlines()
    diff = list(difflib.unified_diff(a, b, fromfile="before", tofile="after", lineterm=""))
    added = sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---"))
    return {"diff": "\n".join(diff) or "(no differences)", "added": added, "removed": removed}


def translate_rule(line: str, target: str) -> dict:
    """Best-effort migration sketch — not a full policy converter."""
    low = line.strip()
    m = re.search(
        r"(permit|deny)\s+(\S+)\s+(\S+)\s+(\S+)(?:\s+eq\s+(\S+))?",
        low,
        re.I,
    )
    action, proto, src, dst, port = ("permit", "ip", "any", "any", None)
    if m:
        action, proto, src, dst, port = m.group(1).lower(), m.group(2), m.group(3), m.group(4), m.group(5)
    port = port or "any"
    sketches = {
        "paloalto": (
            f"set rulebase security rules MIGRATED from {src} to {dst} "
            f"source-user any application {proto if proto != 'ip' else 'any'} "
            f"service {('tcp-' + port) if port != 'any' else 'any'} action {'allow' if action == 'permit' else 'deny'}"
        ),
        "fortinet": (
            f"config firewall policy\nedit 0\n set name MIGRATED\n set srcintf any\n set dstintf any\n"
            f" set srcaddr {src}\n set dstaddr {dst}\n set service {proto.upper() if port == 'any' else proto.upper() + '_' + str(port)}\n"
            f" set action {'accept' if action == 'permit' else 'deny'}\n next\nend"
        ),
        "cisco_asa": f"access-list MIGRATED extended {action} {proto} {src} {dst}"
        + (f" eq {port}" if port != "any" else ""),
        "checkpoint": f"{action} {proto} from {src} to {dst}" + (f" port {port}" if port != "any" else ""),
    }
    if target not in sketches:
        raise ValueError("target must be paloalto, fortinet, cisco_asa, or checkpoint")
    return {"source": line, "target": target, "sketch": sketches[target], "caveat": "Object names, zones, and UTM must be filled in by a human."}


LOOKUPS = {
    "dscp": [
        {"name": "CS0 / BE", "dscp": 0, "cos": 0, "use": "Best effort"},
        {"name": "CS1 / AF11", "dscp": 10, "cos": 1, "use": "Bulk data"},
        {"name": "AF21", "dscp": 18, "cos": 2, "use": "Transactional"},
        {"name": "AF31", "dscp": 26, "cos": 3, "use": "Mission / call signaling"},
        {"name": "AF41", "dscp": 34, "cos": 4, "use": "Interactive video"},
        {"name": "EF", "dscp": 46, "cos": 5, "use": "Voice RTP"},
        {"name": "CS6", "dscp": 48, "cos": 6, "use": "Network control (routing)"},
        {"name": "CS7", "dscp": 56, "cos": 7, "use": "Reserved / spanning-tree"},
    ],
    "ports": [
        {"port": 22, "name": "SSH"},
        {"port": 23, "name": "Telnet"},
        {"port": 49, "name": "TACACS+"},
        {"port": 53, "name": "DNS"},
        {"port": 67, "name": "DHCP server"},
        {"port": 69, "name": "TFTP"},
        {"port": 80, "name": "HTTP"},
        {"port": 123, "name": "NTP"},
        {"port": 161, "name": "SNMP"},
        {"port": 162, "name": "SNMP trap"},
        {"port": 179, "name": "BGP"},
        {"port": 443, "name": "HTTPS / PAN mgmt"},
        {"port": 514, "name": "Syslog"},
        {"port": 1812, "name": "RADIUS auth"},
        {"port": 4500, "name": "IPsec NAT-T"},
        {"port": 500, "name": "IKE"},
        {"port": 8291, "name": "Winbox / some vendors"},
    ],
    "stp": [
        {"priority": 0, "note": "Root — never on an access switch"},
        {"priority": 4096, "note": "Primary core / collapsed core"},
        {"priority": 8192, "note": "Secondary root"},
        {"priority": 16384, "note": "Distribution"},
        {"priority": 32768, "note": "IOS default — leave on access"},
    ],
}


COOKBOOK = {
    "CCNA": [
        {"name": "Int brief", "command": "show ip interface brief", "why": "First look: up/up vs admin down"},
        {"name": "CDP / LLDP", "command": "show cdp neighbors detail\nshow lldp neighbors", "why": "Who is on the other end"},
        {"name": "VLAN + trunk", "command": "show vlan brief\nshow interfaces trunk", "why": "Access vs trunk mistakes"},
        {"name": "STP root", "command": "show spanning-tree root\nshow spanning-tree vlan 1", "why": "Unexpected root = bad night"},
        {"name": "Routes", "command": "show ip route", "why": "Did the prefix land?"},
        {"name": "ARP / MAC", "command": "show ip arp\nshow mac address-table", "why": "L2/L3 mapping"},
    ],
    "CCNP": [
        {"name": "BGP summary", "command": "show ip bgp summary\nshow bgp ipv4 unicast summary", "why": "Idle / Active / Established"},
        {"name": "OSPF neigh", "command": "show ip ospf neighbor\nshow ip ospf interface brief", "why": "2WAY vs FULL, MTU mismatch"},
        {"name": "EIGRP", "command": "show ip eigrp neighbors\nshow ip eigrp topology", "why": "Sia / stuck-in-active"},
        {"name": "EtherChannel", "command": "show etherchannel summary\nshow pagp neighbor", "why": "suspend vs P"},
        {"name": "HSRP/VRRP", "command": "show standby brief\nshow vrrp brief", "why": "Who is active, whose priority"},
        {"name": "First-hop", "command": "show ip cef\nshow adjacency", "why": "CEF vs process switch"},
    ],
    "CCIE": [
        {"name": "Control-plane", "command": "show processes cpu sorted\nshow platform resources\nshow proc cpu history", "why": "Before you blame the WAN"},
        {"name": "FIB / hardware", "command": "show ip cef exact-route 1.1.1.1 8.8.8.8\nshow platform tcam utilization", "why": "Software path vs ASIC"},
        {"name": "CoPP", "command": "show policy-map control-plane\nshow policy-map interface control-plane", "why": "SSH dying under attack"},
        {"name": "BFD", "command": "show bfd neighbors\nshow bfd neighbors details", "why": "Sub-second peer death"},
        {"name": "Multicast", "command": "show ip mroute\nshow ip pim neighbor\nshow ip igmp groups", "why": "RP / SPT issues"},
        {"name": "Don't debug live", "command": "! terminal monitor\n! debug ip packet detail  → use an ACL and logging buffered", "why": "debug ip packet without an ACL takes the box down"},
    ],
    "Security": [
        {"name": "IKE / IPsec", "command": "show crypto ikev2 sa\nshow crypto ipsec sa", "why": "Phase 1 vs 2"},
        {"name": "ASA drops", "command": "show asp drop\nshow conn", "why": "Silent deny"},
        {"name": "AAA", "command": "show aaa servers\ntest aaa group tacacs+ USER pass legacy", "why": "Auth before the change window"},
        {"name": "PAN sessions", "command": "show session all filter destination <ip>\nshow running security-policy", "why": "Which rule hit"},
        {"name": "Forti sessions", "command": "diagnose sys session filter dst <ip>\ndiagnose sys session list", "why": "Policy vs route"},
    ],
}


RUNBOOKS = [
    {
        "id": "fw-cutover",
        "title": "Firewall cutover (ASA/Forti/CP → PAN)",
        "steps": [
            "Export source policy and object groups; freeze rule changes.",
            "Build target policy in lab; run NTerm analyzer + translate sketches.",
            "Pre-stage NAT, routes, IPsec, management, logging host → NTerm syslog.",
            "Backup both boxes to TFTP. Screenshot session counts and top talkers.",
            "Move one transit VLAN or a test host first. Compare sessions.",
            "Cut default route / L2; keep old box powered for 48h failback.",
            "Watch syslog + session table. Disable unused any/any last, not first.",
        ],
    },
    {
        "id": "switch-replace",
        "title": "Access / distribution switch replace",
        "steps": [
            "show run, show vlan, show int trunk, show etherchannel, show spanning-tree root — save logs.",
            "Copy IOS to TFTP/flash on the new unit; same feature set.",
            "Pre-build config: hostname, SVIs, trunks, Portfast/BPDU guard, storm-control, AAA.",
            "Lower STP priority on the new box until it is cabled and verified.",
            "Move uplinks one at a time. Confirm CDP/LLDP and VLAN allow-lists.",
            "Move access bundles. Check MAC table vs old.",
            "Raise STP priority only after dual-home is clean.",
        ],
    },
    {
        "id": "bgp-change",
        "title": "BGP / PE change window",
        "steps": [
            "show ip bgp sum, show ip bgp, show ip route bgp — archive.",
            "soft-reconfig / route-refresh ready? inbound prefix-list staged as inactive.",
            "Apply prefix-list / route-map outbound first on a single neighbor.",
            "clear ip bgp x.x.x.x soft in/out — never hard reset unless you mean it.",
            "Compare received/advertised counts. Look for 0.0.0.0/0 surprises.",
            "Only then clone to the rest of the neighbors.",
        ],
    },
    {
        "id": "prechange",
        "title": "Universal pre-change",
        "steps": [
            "Who is the rollback owner and what is the exact revert command?",
            "terminal length 0; show run; write mem; copy run tftp.",
            "NTP, logging, AAA still work from the jump path you will use at 2am.",
            "Confirm you are on the right VDC/VRF/context/vsys/VDOM.",
            "No debug without an ACL. No write erase. No reload in.",
        ],
    },
]
