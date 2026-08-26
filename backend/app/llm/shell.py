"""Shell-command drafting for local and Linux/Windows sessions.

The network tools in tools.py are a fixed, well-shaped set. Shell work is
open-ended, so it gets one tool whose argument IS the command — which means the
safety burden moves from "did the model pick the right tool" to "is this command
about to destroy something".

Two rules hold here, both deliberate:

1. A drafted shell command is NEVER auto-applied. act() auto-applies low-risk
   show_status on network gear; shell is excluded unconditionally. "If you
   didn't see it, it didn't go" has to mean something on a box with rm.
2. Destructive shapes are forced to high risk regardless of what the model
   claims, because the model is the thing we are guarding against.
"""
from __future__ import annotations

import re

BASH = "bash"
POWERSHELL = "powershell"


def dialect_for(device_type: str | None, kind: str | None = None) -> str:
    """Map a session to a shell dialect."""
    dt = (device_type or "").lower()
    if dt in ("windows", "powershell", "win"):
        return POWERSHELL
    return BASH


# Shapes that can ruin someone's evening. Matched against the whole command, so
# a destructive verb buried in a pipeline is still caught.
_DESTRUCTIVE = [
    (re.compile(r"\brm\s+(-\w*\s+)*-\w*[rf]", re.I), "recursive/forced delete"),
    (re.compile(r"\brm\s+-rf?\s+/(?:\s|$)", re.I), "delete from filesystem root"),
    (re.compile(r"\b(mkfs|fdisk|parted|wipefs)\b", re.I), "filesystem/partition write"),
    (re.compile(r"\bdd\s+.*\bof=/dev/", re.I), "raw write to a block device"),
    (re.compile(r">\s*/dev/(sd|nvme|hd)", re.I), "redirect onto a block device"),
    (re.compile(r"\b(shutdown|reboot|halt|poweroff|init\s+0)\b", re.I), "host restart/shutdown"),
    (re.compile(r"\bchmod\s+-R\s+777\b", re.I), "world-writable recursive chmod"),
    (re.compile(r"\bchown\s+-R\b.*\s/(?:\s|$)", re.I), "recursive chown from root"),
    (re.compile(r":\(\)\s*\{.*\};\s*:", re.S), "fork bomb"),
    (re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba)?sh", re.I), "pipe from network into a shell"),
    (re.compile(r"\btruncate\s+-s\s*0\b", re.I), "truncate file to zero"),
    # PowerShell
    (re.compile(r"Remove-Item\b.*-Recurse", re.I), "recursive delete"),
    (re.compile(r"\b(Format-Volume|Clear-Disk|Initialize-Disk)\b", re.I), "disk format/clear"),
    (re.compile(r"\b(Stop-Computer|Restart-Computer)\b", re.I), "host restart/shutdown"),
    (re.compile(r"Set-ExecutionPolicy\s+Unrestricted", re.I), "disables script signing policy"),
    (re.compile(r"Invoke-(Expression|WebRequest)\b.*\|\s*iex", re.I), "download and execute"),
    (re.compile(r"\brmdir\s+/s\b", re.I), "recursive directory delete"),
    (re.compile(r"\bdel\s+/[sfq]", re.I), "forced delete"),
]

# Commands that only read. Used to LABEL, never to skip confirmation.
_READ_ONLY = re.compile(
    r"^\s*(ls|ll|cat|less|more|head|tail|grep|find|df|du|ps|top|free|uptime|who|id|pwd|"
    r"ip\b|ifconfig|netstat|ss|ping|traceroute|dig|nslookup|systemctl\s+status|journalctl|"
    r"uname|lsblk|mount\s*$|date|env|printenv|which|whereis|stat|file|wc|sort|uniq|"
    r"Get-\w+|Test-\w+|Measure-\w+|Select-\w+)\b",
    re.I,
)


def classify(command: str) -> tuple[str, list[str]]:
    """Return (risk, reasons). Destructive shapes always win."""
    reasons = [why for pat, why in _DESTRUCTIVE if pat.search(command)]
    if reasons:
        return "high", reasons
    if _READ_ONLY.match(command.strip()):
        return "low", []
    return "medium", []


def render(args: dict, dialect: str) -> tuple[list[str], str, str]:
    """Render a shell_command tool call. Signature matches adapters._* helpers."""
    command = (args.get("command") or "").strip()
    if not command:
        raise ValueError("shell_command requires a command")

    explanation = (args.get("explanation") or "").strip()
    risk, reasons = classify(command)

    shell = POWERSHELL if dialect in (POWERSHELL, "windows") else BASH
    summary = explanation or ("PowerShell" if shell == POWERSHELL else "Shell") + " command"
    if reasons:
        summary += "  ⚠ " + "; ".join(reasons)

    return [command], summary, risk
