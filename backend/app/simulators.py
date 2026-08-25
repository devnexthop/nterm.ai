"""Offline device CLIs so NTerm is usable without a lab."""

from __future__ import annotations


class DeviceSimulator:
    def __init__(self, device_type: str, hostname: str):
        self.device_type = device_type
        self.hostname = hostname
        self.mode = "login"
        self.username = ""
        self.config_mode = False
        self.buffer = ""
        self.banner = self._banner()

    def _banner(self) -> str:
        if self.device_type.startswith("cisco"):
            return (
                "\r\nUser Access Verification\r\n\r\n"
                "Username: "
            )
        if self.device_type == "paloalto":
            return "\r\nPalo Alto Networks PAN-OS\r\nlogin: "
        if self.device_type == "fortinet":
            return "\r\nFortiGate login: "
        return f"\r\n{self.hostname} login: "

    def prompt(self) -> str:
        if self.device_type.startswith("cisco"):
            suffix = "(config)#" if self.config_mode else ("#" if self.mode == "enable" else ">")
            return f"{self.hostname}{suffix}"
        if self.device_type == "paloalto":
            return f"{self.username}@{self.hostname}> "
        if self.device_type == "fortinet":
            return f"{self.hostname} # "
        return f"{self.hostname}$ "

    def feed(self, data: str) -> str:
        out = []
        for ch in data:
            if ch in ("\r", "\n"):
                line = self.buffer
                self.buffer = ""
                out.append("\r\n")
                out.append(self._handle(line.strip()))
            elif ch == "\x7f" or ch == "\b":
                if self.buffer:
                    self.buffer = self.buffer[:-1]
                    out.append("\b \b")
            elif ch == "\x03":
                self.buffer = ""
                self.config_mode = False
                out.append("^C\r\n" + self.prompt())
            else:
                if ch.isprintable():
                    self.buffer += ch
                    out.append(ch)
        return "".join(out)

    def _handle(self, line: str) -> str:
        if self.mode == "login":
            self.username = line or "admin"
            self.mode = "password"
            return "Password: "
        if self.mode == "password":
            self.mode = "enable" if self.device_type.startswith("cisco") else "exec"
            if self.device_type.startswith("cisco"):
                self.mode = "user"
            return self._motd() + self.prompt()
        if self.device_type.startswith("cisco"):
            return self._cisco(line)
        if self.device_type == "paloalto":
            return self._pan(line)
        if self.device_type == "fortinet":
            return self._forti(line)
        return self._unix(line)

    def _motd(self) -> str:
        if self.device_type.startswith("cisco"):
            return (
                "\r\n************************************************\r\n"
                f"* NTerm simulator — {self.hostname} ({self.device_type})\r\n"
                "* Not a real device. Safe for broadcast / AI tests.\r\n"
                "************************************************\r\n"
            )
        return f"\r\nWelcome to {self.hostname} (NTerm simulator)\r\n"

    def _cisco(self, line: str) -> str:
        low = line.lower()
        if low in ("?", "help"):
            return (
                "  enable            Enter privileged mode\r\n"
                "  show version      Software / hardware\r\n"
                "  show ip interface brief\r\n"
                "  show running-config\r\n"
                "  show cdp neighbors\r\n"
                "  configure terminal\r\n"
                "  terminal length 0\r\n"
                + self.prompt()
            )
        if low in ("en", "enable"):
            self.mode = "enable"
            return self.prompt()
        if low in ("disable", "exit") and not self.config_mode:
            if self.mode == "enable":
                self.mode = "user"
            return self.prompt()
        if low in ("conf t", "configure terminal", "config t"):
            if self.mode != "enable":
                return "% Privileged command.\r\n" + self.prompt()
            self.config_mode = True
            return self.prompt()
        if low in ("end", "exit") and self.config_mode:
            self.config_mode = False
            return self.prompt()
        if low.startswith("terminal "):
            return self.prompt()
        if low in ("show version", "sh ver", "show ver"):
            return (
                f"{self.hostname} uptime is 3 days, 4 hours\r\n"
                "Cisco IOS XE Software, Version 17.09.04a (simulator)\r\n"
                "License Level: ax\r\n"
                + self.prompt()
            )
        if "ip int" in low or "ip interface brief" in low:
            return (
                "Interface              IP-Address      OK? Method Status                Protocol\r\n"
                "GigabitEthernet0/0     10.10.10.1      YES NVRAM  up                    up\r\n"
                "GigabitEthernet0/1     10.20.20.1      YES NVRAM  up                    up\r\n"
                "GigabitEthernet0/2     unassigned      YES NVRAM  down                  down\r\n"
                "Loopback0              1.1.1.1         YES NVRAM  up                    up\r\n"
                + self.prompt()
            )
        if "cdp" in low:
            return (
                "Capability Codes: R - Router, S - Switch\r\n"
                "Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID\r\n"
                "CORE-SW          Gig 0/1           140        S           9300      Gig 1/0/1\r\n"
                + self.prompt()
            )
        if "running-config" in low or low in ("sh run", "show run"):
            return (
                "Building configuration...\r\n"
                f"hostname {self.hostname}\r\n"
                "!\r\n"
                "enable secret 5 $1$relay$simulator\r\n"
                "!\r\n"
                "interface GigabitEthernet0/0\r\n"
                " ip address 10.10.10.1 255.255.255.0\r\n"
                " no shutdown\r\n"
                "!\r\n"
                "interface GigabitEthernet0/1\r\n"
                " ip address 10.20.20.1 255.255.255.0\r\n"
                "!\r\n"
                "interface GigabitEthernet0/2\r\n"
                " shutdown\r\n"
                "!\r\n"
                "ip http server\r\n"
                "snmp-server community public ro\r\n"
                "line vty 0 4\r\n"
                " password cisco\r\n"
                " login\r\n"
                " transport input telnet ssh\r\n"
                "!\r\nend\r\n"
                + self.prompt()
            )
        if not line:
            return self.prompt()
        return f"% Unknown command or simulator stub: {line}\r\n" + self.prompt()

    def _pan(self, line: str) -> str:
        low = line.lower()
        if low in ("?", "help"):
            return (
                "  show system info\r\n  show interface all\r\n"
                "  show routing route\r\n  configure\r\n" + self.prompt()
            )
        if low == "configure":
            self.config_mode = True
            return self.prompt().replace(">", "#")
        if "system info" in low:
            return (
                f"hostname: {self.hostname}\r\n"
                "ip-address: 10.8.8.10\r\nmodel: PA-VM\r\nsw-version: 11.1.2 (simulator)\r\n"
                + self.prompt()
            )
        if "interface" in low:
            return (
                "name     id    speed/duplex/state        ip\r\n"
                "ethernet1/1  16  1000/full/up            10.8.8.10/24\r\n"
                "ethernet1/2  17  auto/auto/down          0.0.0.0/0\r\n"
                + self.prompt()
            )
        if not line:
            return self.prompt()
        return f"Unknown command: {line}\r\n" + self.prompt()

    def _forti(self, line: str) -> str:
        low = line.lower()
        if low in ("?", "help"):
            return "  get system status\r\n  get system interface\r\n  config system console\r\n" + self.prompt()
        if "system status" in low:
            return (
                f"Version: FortiGate-VM v7.4.3 (simulator)\r\n"
                f"Hostname: {self.hostname}\r\nOperation Mode: NAT\r\n"
                + self.prompt()
            )
        if "system interface" in low:
            return (
                "== [ port1 ]\r\n"
                "ip: 10.9.9.1 255.255.255.0  status: up\r\n"
                "== [ port2 ]\r\n"
                "ip: 0.0.0.0 0.0.0.0  status: down\r\n"
                + self.prompt()
            )
        if not line:
            return self.prompt()
        return f"Unknown action {line}\r\n" + self.prompt()

    def _unix(self, line: str) -> str:
        if line in ("help", "?"):
            return "NTerm local simulator. Try: hostname, uname -a, ip addr\r\n" + self.prompt()
        if line == "hostname":
            return self.hostname + "\r\n" + self.prompt()
        if line == "uname -a":
            return "Linux relay 6.8.0 simulator x86_64 GNU/Linux\r\n" + self.prompt()
        if not line:
            return self.prompt()
        return f"sh: {line}: not found\r\n" + self.prompt()
