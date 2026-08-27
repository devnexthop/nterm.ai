from __future__ import annotations

import ipaddress
import re

from . import shell


def _mask(cidr: str) -> tuple[str, str]:
    """Network address + mask. Right for routes and DHCP scopes."""
    net = ipaddress.ip_network(cidr, strict=False)
    if net.version != 4:
        raise ValueError("IPv4 CIDR required")
    return str(net.network_address), str(net.netmask)


def _host_mask(cidr: str) -> tuple[str, str]:
    """Host address + mask. Right for an interface.

    An interface is configured with the address you asked for, not the network
    it sits in — `1.1.1.1/24` must produce `ip address 1.1.1.1 255.255.255.0`.
    Using the network address here silently gave `1.1.1.0`, which is a different
    (and on a /24, unusable) address to the one the operator typed.
    """
    iface = ipaddress.ip_interface(cidr)
    if iface.version != 4:
        raise ValueError("IPv4 CIDR required")
    return str(iface.ip), str(iface.network.netmask)


def render(tool: str, args: dict, dialect: str) -> dict:
    d = dialect or "cisco_ios"
    fn = {
        "set_interface_ip": _iface,
        "dhcp_pool": _dhcp,
        "palo_rule": _palo,
        "forti_vip": _vip,
        "static_route": _route,
        "show_status": _show,
        "shell_command": lambda a, d: shell.render(a, d),
    }.get(tool)
    if not fn:
        raise ValueError(f"Unknown tool {tool}")
    commands, summary, risk = fn(args, d)
    return {"tool": tool, "args": args, "commands": commands, "summary": summary, "risk": risk, "dialect": d}


def _iface(args: dict, d: str) -> tuple[list[str], str, str]:
    iface = args.get("interface") or args.get("if") or "Loopback0"
    cidr = args.get("cidr") or args.get("address") or ""
    net, mask = _host_mask(cidr)
    if d.startswith("cisco"):
        cmds = ["configure terminal", f"interface {iface}", f"ip address {net} {mask}", "no shutdown", "end"]
    elif d == "paloalto":
        cmds = [
            "configure",
            f"set network interface ethernet {iface} layer3 ip {cidr}",
            "commit",
        ]
    elif d == "fortinet":
        cmds = [
            "config system interface",
            f"edit {iface}",
            f"set ip {net} {mask}",
            "set status up",
            "next",
            "end",
        ]
    else:
        cmds = [f"ip addr add {cidr} dev {iface}"]
    return cmds, f"Set {iface} to {cidr}", "medium"


def _dhcp(args: dict, d: str) -> tuple[list[str], str, str]:
    name = args.get("name") or "LAB"
    cidr = args.get("cidr") or "10.10.10.0/24"
    gw = args.get("gateway") or args.get("router") or ""
    dns = args.get("dns") or gw
    net, mask = _mask(cidr)
    if d.startswith("cisco"):
        cmds = ["configure terminal", f"ip dhcp pool {name}", f"network {net} {mask}"]
        if gw:
            cmds.append(f"default-router {gw}")
        if dns:
            cmds.append(f"dns-server {dns}")
        cmds.append("end")
    elif d == "fortinet":
        cmds = ["config system dhcp server", "edit 0", f"set dns-service default", f"set default-gateway {gw}", "next", "end"]
    else:
        cmds = [f"! DHCP pool {name} {cidr} gw {gw}"]
    return cmds, f"DHCP pool {name} {cidr}", "medium"


def _palo(args: dict, d: str) -> tuple[list[str], str, str]:
    name = args.get("name") or "nterm-allow"
    src = args.get("source") or "any"
    dst = args.get("destination") or "any"
    app = args.get("app") or "any"
    action = args.get("action") or "allow"
    frm = args.get("from_zone") or "any"
    to = args.get("to_zone") or "any"
    cmds = [
        "configure",
        f"set rulebase security rules {name} from {frm}",
        f"set rulebase security rules {name} to {to}",
        f"set rulebase security rules {name} source {src}",
        f"set rulebase security rules {name} destination {dst}",
        f"set rulebase security rules {name} application {app}",
        f"set rulebase security rules {name} service application-default",
        f"set rulebase security rules {name} action {action}",
        "commit",
    ]
    return cmds, f"PAN rule {name} {action}", "high"


def _vip(args: dict, d: str) -> tuple[list[str], str, str]:
    name = args.get("name") or "web-ext"
    ext = args.get("extip") or args.get("external") or ""
    mapped = args.get("mappedip") or args.get("mapped") or ""
    port = str(args.get("port") or "443")
    cmds = [
        "config firewall vip",
        f"edit {name}",
        f"set extip {ext}",
        "set extintf any",
        f"set mappedip {mapped}",
        "set portforward enable",
        f"set protocol tcp",
        f"set extport {port}",
        f"set mappedport {port}",
        "next",
        "end",
    ]
    return cmds, f"Forti VIP {name} {ext} -> {mapped}:{port}", "high"


def _route(args: dict, d: str) -> tuple[list[str], str, str]:
    cidr = args.get("cidr") or args.get("prefix") or ""
    nh = args.get("nexthop") or args.get("via") or ""
    net, mask = _mask(cidr)
    if d.startswith("cisco"):
        cmds = ["configure terminal", f"ip route {net} {mask} {nh}", "end"]
    elif d == "paloalto":
        cmds = ["configure", f"set network virtual-router default routing-table ip static-route nterm-r destination {cidr} nexthop ip-address {nh}", "commit"]
    else:
        cmds = ["config router static", "edit 0", f"set dst {cidr}", f"set gateway {nh}", "next", "end"]
    return cmds, f"Static route {cidr} via {nh}", "medium"


def _show(args: dict, d: str) -> tuple[list[str], str, str]:
    if d.startswith("cisco"):
        cmds = ["show ip interface brief"]
    elif d == "paloalto":
        cmds = ["show interface all"]
    elif d == "fortinet":
        cmds = ["get system interface"]
    else:
        cmds = ["ip addr"]
    return cmds, "Status (read-only)", "low"


def heuristic(message: str, dialect: str) -> dict | None:
    q = message.lower()
    cidr = None
    m = re.search(r"(\d+\.\d+\.\d+\.\d+\s*/\s*\d+)", message)
    if m:
        cidr = m.group(1).replace(" ", "")
    iface = None
    im = re.search(r"(loopback\s*\d+|gi\s*\d+/\d+|gigabitethernet\s*\S+|ethernet\s*\S+|port\d+)", q)
    if im:
        iface = im.group(1).replace(" ", "")
        if iface.startswith("gi") and "/" in iface:
            iface = "GigabitEthernet" + iface[2:]
        elif iface.startswith("loopback"):
            iface = "Loopback" + re.sub(r"\D", "", iface)
    if cidr and ("interface" in q or "ip address" in q or iface or "set " in q):
        return render("set_interface_ip", {"interface": iface or "Loopback0", "cidr": cidr}, dialect)
    if "dhcp" in q and cidr:
        gw = None
        gm = re.search(r"gateway\s+(\d+\.\d+\.\d+\.\d+)", q)
        if gm:
            gw = gm.group(1)
        name_m = re.search(r"pool\s+(\S+)", q)
        return render("dhcp_pool", {"name": (name_m.group(1) if name_m else "LAB").strip(",."), "cidr": cidr, "gateway": gw or ""}, dialect)
    if "vip" in q or "virtual ip" in q:
        ips = re.findall(r"\d+\.\d+\.\d+\.\d+", message)
        port_m = re.search(r":(\d{2,5})", message)
        return render("forti_vip", {"name": "web-ext", "extip": ips[0] if ips else "", "mappedip": ips[1] if len(ips) > 1 else "", "port": port_m.group(1) if port_m else "443"}, dialect)
    if "security rule" in q or ("allow" in q and ("palo" in q or dialect == "paloalto" or "dns" in q)):
        ips = re.findall(r"\d+\.\d+\.\d+\.\d+(?:/\d+)?", message)
        app_m = re.search(r"app\s+(\S+)", q)
        return render("palo_rule", {"source": ips[0] if ips else "any", "destination": ips[1] if len(ips) > 1 else "any", "app": app_m.group(1) if app_m else "any", "action": "allow"}, dialect)
    if "static route" in q or q.startswith("route "):
        ips = re.findall(r"\d+\.\d+\.\d+\.\d+(?:/\d+)?", message)
        return render("static_route", {"cidr": ips[0] if ips else "0.0.0.0/0", "nexthop": ips[1] if len(ips) > 1 else ""}, dialect)
    if "show" in q and ("int" in q or "status" in q or "brief" in q):
        return render("show_status", {}, dialect)
    return None
