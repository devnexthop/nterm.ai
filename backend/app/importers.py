"""Parsers for session inventories exported from other terminals.

Nobody retypes 200 sessions by hand, so the first thing a SecureCRT or PuTTY
user needs is a way to bring an existing estate across. Each parser here reads
*structure only* -- host, port, protocol, username, folder.

Stored secrets are deliberately never touched. SecureCRT's obfuscated password
blobs and PuTTY's proxy passwords are skipped rather than decoded: an import
must not quietly lift a credential out of the tool the operator chose to keep
it in, and NTerm's vault should only ever hold secrets a human typed into it.

Every parser returns a list of plain dicts with the same shape, so the preview
UI and the commit endpoint do not care which terminal a file came from:

    name, host, port, kind ("ssh" | "telnet" | "serial"),
    username, device_type, group, baud
"""

from __future__ import annotations

import csv
import io
import re
from urllib.parse import unquote

from .device_profiles import PROFILES

FORMATS = ("securecrt", "putty", "sshconfig", "csv", "nterm")

# A pasted inventory is text an operator typed or exported; anything past these
# bounds is a mistake or an attack, not a session list. Enforced by the caller.
MAX_CONTENT_BYTES = 4 * 1024 * 1024
MAX_SESSIONS = 5000

DEFAULT_PORTS = {"ssh": 22, "telnet": 23, "serial": 22}

_MAX_NAME = 200
_MAX_HOST = 255
_MAX_USER = 200

# rlogin and raw are plain TCP byte streams and NTerm has no separate transport
# for either, so they land on telnet -- the closest pane it can actually open.
# Anything absent from this table (RDP, TAPI, dial-up) is dropped instead of
# guessed at, because importing it would create a session that can never open.
_PROTOCOLS = {
    "ssh": "ssh",
    "ssh1": "ssh",
    "ssh2": "ssh",
    "sftp": "ssh",
    "telnet": "telnet",
    "telnets": "telnet",
    "telnet/ssl": "telnet",
    "rlogin": "telnet",
    "raw": "telnet",
    "serial": "serial",
}

# Vendor spellings seen in the wild, mapped onto NTerm's device profiles. Order
# matters: the specific platforms come before the ones whose tokens they share.
_VENDOR_TOKENS = (
    ("cisco_nxos", ("nxos", "nexus", "n9k", "n7k", "n5k", "n3k", "n2k")),
    ("cisco_asa", ("asa", "asav", "ftd", "firepower", "fpr", "asdm")),
    ("cisco_ios", ("ios", "iosxe", "iosxr", "cisco", "catalyst", "isr", "csr", "c9k", "cat9k")),
    ("paloalto", ("paloalto", "panos", "panorama", "palo", "panw", "pavm")),
    ("fortinet", ("fortinet", "fortios", "fortigate", "fortimanager", "forti", "fgt")),
    ("juniper", ("juniper", "junos", "srx", "qfx", "vsrx")),
    ("windows", ("windows", "powershell", "winrm", "win")),
    ("linux", ("linux", "ubuntu", "debian", "centos", "rhel", "unix", "bsd")),
)

_SERIAL_DEVICE = re.compile(r"^(?:com\d+|/dev/tty\S*|/dev/cu\.\S+)$", re.I)

# SecureCRT lines are typed: S: string, D: dword (hex), B: bool, Z: blob.
_CRT_LINE = re.compile(r'^\s*([A-Z]):"([^"]*)"=(.*)$')
_CRT_FILE_MARKER = re.compile(r"^\s*(?:[#;]+|//)\s*(?:file:\s*)?(?P<path>\S.*\.ini)\s*$", re.I)
_CRT_SECTION = re.compile(r"^\s*\[(?P<path>[^\]]+)\]\s*$")
_SECRET_KEY = re.compile(r"pass(word|phrase)|secret|\bkey\b", re.I)

_REG_SECTION = re.compile(r"^\s*\[(?P<key>[^\]]+)\]\s*$")
_REG_VALUE = re.compile(r'^\s*"(?P<name>(?:[^"\\]|\\.)*)"\s*=\s*(?P<value>.*)$')
_PUTTY_SESSION = re.compile(r"SimonTatham[\\/]+PuTTY[\\/]+Sessions[\\/]+(?P<name>.+)$", re.I)
# A whitelist, so a proxy password is never even read into memory.
_PUTTY_KEYS = {"hostname", "portnumber", "protocol", "username", "serialline", "serialspeed"}

_SSH_OPTION = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)\s*(?:=\s*|\s+)(.*)$")
_SSH_TOKENS = re.compile(r'"([^"]*)"|(\S+)')


# --------------------------------------------------------------------------
# shared normalisation
# --------------------------------------------------------------------------


def _clean(value: object, limit: int) -> str:
    text = "" if value is None else str(value)
    return text.strip().strip('"').strip()[:limit]


def _port(value: object, kind: str) -> int:
    digits = re.match(r"\s*(\d+)", str(value or ""))
    port = int(digits.group(1)) if digits else 0
    if not 1 <= port <= 65535:
        return DEFAULT_PORTS.get(kind, 22)
    return port


def _baud(value: object) -> int:
    digits = re.match(r"\s*(\d+)", str(value or ""))
    baud = int(digits.group(1)) if digits else 0
    return baud if 50 <= baud <= 4_000_000 else 9600


def _match_vendor(text: str) -> str:
    lowered = (text or "").lower()
    tokens = {t for t in re.split(r"[^a-z0-9]+", lowered) if t}
    flat = re.sub(r"[^a-z0-9]+", "", lowered)
    for device_type, needles in _VENDOR_TOKENS:
        for needle in needles:
            # Substring matching is reserved for needles long enough to be
            # unambiguous: "asa" as a substring would flag every host in Kansas.
            if needle in tokens or needle == flat or (len(needle) >= 5 and needle in flat):
                return device_type
    return ""


def _device_type(explicit: str = "", hint: str = "") -> str:
    declared = (explicit or "").strip().lower().replace(" ", "_").replace("-", "_")
    if declared in PROFILES:
        return declared
    if explicit:
        found = _match_vendor(explicit)
        if found:
            return found
        return "generic"
    # SecureCRT, PuTTY and ssh_config carry no vendor field at all. Reading the
    # session name back is a guess, but a wrong guess only costs one paging
    # command, while leaving 200 imported rows as "generic" costs 200 edits.
    return _match_vendor(hint) or "generic"


def _row(
    name: str,
    host: str,
    port: object = None,
    kind: str = "ssh",
    username: str = "",
    device_type: str = "",
    group: str = "",
    baud: object = 9600,
) -> dict:
    kind = kind if kind in DEFAULT_PORTS else "ssh"
    host = _clean(host, _MAX_HOST)
    name = _clean(name, _MAX_NAME) or host
    group = _clean(group, _MAX_NAME)
    if kind != "serial" and _SERIAL_DEVICE.match(host):
        kind = "serial"
    return {
        "name": name,
        "host": host,
        "port": _port(port, kind),
        "kind": kind,
        "username": _clean(username, _MAX_USER),
        "device_type": _device_type(device_type, f"{name} {host} {group}"),
        "group": group,
        "baud": _baud(baud),
    }


def _split_group(label: str) -> tuple[str, str]:
    """Split "Acme\\Core\\SW-01" into ("Acme/Core", "SW-01")."""
    parts = [p.strip() for p in re.split(r"[\\/]+", label or "") if p.strip()]
    if not parts:
        return "", ""
    return "/".join(parts[:-1]), parts[-1]


# --------------------------------------------------------------------------
# SecureCRT
# --------------------------------------------------------------------------


def _crt_path_parts(path: str) -> tuple[str, str]:
    parts = [p.strip() for p in re.split(r"[\\/]+", path or "") if p.strip() not in ("", ".")]
    if not parts:
        return "", ""
    name = re.sub(r"\.ini$", "", parts[-1], flags=re.I)
    folders = parts[:-1]
    # Everything above SecureCRT's own "Sessions" directory is install plumbing
    # (Config, AppData, a drive letter); only the tree below it is the
    # operator's filing system, and that is what becomes the group.
    for i, folder in enumerate(folders):
        if folder.lower() == "sessions":
            folders = folders[i + 1 :]
            break
    return "/".join(folders), name


def _crt_row(strings: dict, dwords: dict, path: str) -> dict | None:
    kind = _PROTOCOLS.get(strings.get("Protocol Name", "SSH2").strip().lower(), "")
    if not kind:
        return None
    group, name = _crt_path_parts(path)
    if name.lower().startswith("__") or name.lower() == "default":
        return None
    if kind == "serial":
        # A serial session keeps its device in the *string* "Port" ("COM3");
        # a network session keeps a TCP number in the dword of the same name.
        host = strings.get("Port", "") or strings.get("Serial Port", "") or strings.get("Line", "")
        port = DEFAULT_PORTS["serial"]
    else:
        host = strings.get("Hostname", "")
        port = dwords.get("Port", 0)
    if not host.strip():
        return None
    return _row(
        name=name or host,
        host=host,
        port=port,
        kind=kind,
        username=strings.get("Username", ""),
        group=group,
        baud=dwords.get("Baud Rate", 9600),
    )


def parse_securecrt(content: str, filename: str = "") -> list[dict]:
    """Parse one SecureCRT ``.ini`` session file, or a bundle of them.

    A single file carries no folder information -- the group lives in the path
    under ``Sessions/``. So a whole tree can be handed over as one document
    where each file is introduced by its relative path, either as a comment
    (``# Sessions/Acme/Core-SW-01.ini``) or as a section header
    (``[Sessions/Acme/Core-SW-01]``); everything up to the next marker belongs
    to that session.
    """
    rows: list[dict] = []
    path = filename or ""
    strings: dict[str, str] = {}
    dwords: dict[str, int] = {}

    def flush() -> None:
        nonlocal strings, dwords, path
        if strings or dwords:
            row = _crt_row(strings, dwords, path)
            if row:
                rows.append(row)
        strings, dwords, path = {}, {}, ""

    for raw in (content or "").splitlines():
        line = raw.rstrip("\r").lstrip("﻿")
        marker = _CRT_FILE_MARKER.match(line) or _CRT_SECTION.match(line)
        if marker:
            flush()
            path = marker.group("path").strip()
            continue
        field = _CRT_LINE.match(line)
        if not field:
            continue
        vtype, key, value = field.group(1), field.group(2), field.group(3)
        if _SECRET_KEY.search(key):
            continue
        if vtype == "S":
            strings[key] = value.strip()
        elif vtype in ("D", "B"):
            try:
                dwords[key] = int(value.strip() or "0", 16)
            except ValueError:
                continue
    flush()
    return rows


# --------------------------------------------------------------------------
# PuTTY
# --------------------------------------------------------------------------


def _unescape_reg(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def _reg_value(raw: str) -> object:
    raw = raw.strip()
    if raw.startswith('"'):
        end = raw.rfind('"')
        return _unescape_reg(raw[1:end] if end > 0 else raw[1:])
    lowered = raw.lower()
    if lowered.startswith("dword:"):
        try:
            return int(raw.split(":", 1)[1].strip(), 16)
        except ValueError:
            return 0
    if lowered.startswith(("hex(1):", "hex(2):", "hex(7):")):
        blob = bytes(int(b, 16) for b in re.findall(r"[0-9a-fA-F]{2}", raw.split(":", 1)[1]))
        return blob.decode("utf-16-le", "ignore").split("\x00")[0]
    if lowered.startswith("hex"):
        return ""
    return raw


def _join_reg_continuations(text: str) -> list[str]:
    """regedit wraps long values with a trailing backslash; rejoin them."""
    lines: list[str] = []
    pending = ""
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if pending:
            line = pending + line.strip()
            pending = ""
        if line.rstrip().endswith("\\"):
            pending = line.rstrip()[:-1]
            continue
        lines.append(line)
    if pending:
        lines.append(pending)
    return lines


def _putty_row(label: str, values: dict) -> dict | None:
    if not label or label.strip().lower() == "default settings":
        return None
    kind = _PROTOCOLS.get(str(values.get("protocol", "ssh") or "ssh").strip().lower(), "")
    if not kind:
        return None
    group, name = _split_group(label)
    username = str(values.get("username", "") or "")
    if kind == "serial":
        host = str(values.get("serialline", "") or "")
        port = DEFAULT_PORTS["serial"]
    else:
        host = str(values.get("hostname", "") or "")
        port = values.get("portnumber", 0)
    # PuTTY lets the host box carry "user@host" and stores it verbatim; the two
    # have to come apart again or the username is lost and the host is unusable.
    if "@" in host:
        head, _, tail = host.partition("@")
        if tail:
            host, username = tail, username or head
    if not host.strip():
        return None
    return _row(
        name=name or host,
        host=host,
        port=port,
        kind=kind,
        username=username,
        group=group,
        baud=values.get("serialspeed", 9600),
    )


def parse_putty(content: str, filename: str = "") -> list[dict]:
    """Parse a registry export of ``HKCU\\...\\SimonTatham\\PuTTY\\Sessions``."""
    rows: list[dict] = []
    values: dict | None = None
    label = ""

    for line in _join_reg_continuations(content or ""):
        section = _REG_SECTION.match(line)
        if section:
            if values is not None:
                row = _putty_row(label, values)
                if row:
                    rows.append(row)
            values, label = None, ""
            key = section.group("key").strip()
            if key.startswith("-"):  # regedit's "delete this key" form
                continue
            found = _PUTTY_SESSION.search(key)
            if found:
                # PuTTY percent-escapes anything outside [A-Za-z0-9] in the key
                # name, so "%20" is a space and "%5C" is the folder separator
                # that PuTTY forks use for grouping.
                label = unquote(found.group("name").strip())
                values = {}
            continue
        if values is None:
            continue
        field = _REG_VALUE.match(line)
        if not field:
            continue
        name = _unescape_reg(field.group("name")).lower()
        if name in _PUTTY_KEYS:
            values[name] = _reg_value(field.group("value"))

    if values is not None:
        row = _putty_row(label, values)
        if row:
            rows.append(row)
    return rows


# --------------------------------------------------------------------------
# OpenSSH config
# --------------------------------------------------------------------------


def _ssh_tokens(value: str) -> list[str]:
    return [quoted or bare for quoted, bare in _SSH_TOKENS.findall(value)]


def parse_ssh_config(content: str, filename: str = "") -> list[dict]:
    """Parse ``~/.ssh/config`` Host blocks into sessions."""
    rows: list[dict] = []
    aliases: list[str] = []
    options: dict[str, str] = {}

    def flush() -> None:
        for alias in aliases:
            # "Host *" and friends set defaults for other blocks; they are not
            # hosts anyone can connect to, and negations exclude rather than
            # define. Importing them would create unreachable sessions.
            if any(ch in alias for ch in "*?!"):
                continue
            host = options.get("hostname", "") or alias
            # %h / %p / %r only resolve at connect time, so a templated
            # HostName cannot be stored -- fall back to the alias, which ssh
            # itself would have used had HostName been absent.
            if "%" in host:
                host = alias
            rows.append(
                _row(
                    name=alias,
                    host=host,
                    port=options.get("port", 0),
                    kind="ssh",
                    username=options.get("user", ""),
                    group="",
                )
            )

    for raw in (content or "").splitlines():
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        field = _SSH_OPTION.match(line)
        if not field:
            continue
        keyword, value = field.group(1).lower(), field.group(2).strip()
        if keyword == "host":
            flush()
            aliases, options = _ssh_tokens(value), {}
        elif keyword == "match":
            # A Match block's options are conditional; attributing them to the
            # preceding Host would be wrong, so the block simply ends here.
            flush()
            aliases, options = [], {}
        elif aliases and keyword in ("hostname", "port", "user"):
            tokens = _ssh_tokens(value)
            if tokens:
                options.setdefault(keyword, tokens[0])
    flush()
    return [row for row in rows if row["host"]]


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------

# Aliases are written in normalised form: lower case, separators collapsed to
# single spaces, so "Device_Type", "device-type" and "DEVICE TYPE" all land here.
_CSV_COLUMNS = (
    ("host", ("host", "hostname", "host name", "ip", "ip address", "ipaddress", "address",
              "mgmt ip", "management ip", "primary ip", "fqdn", "dns", "dns name", "target")),
    ("port", ("port", "ssh port", "tcp port", "portnumber", "port number")),
    ("username", ("username", "user", "user name", "login", "account", "ssh user", "userid")),
    ("device_type", ("device type", "devicetype", "vendor", "platform", "os", "type", "make",
                     "model", "driver", "netmiko", "netmiko driver", "napalm", "manufacturer")),
    ("group", ("group", "folder", "customer", "client", "site", "tenant", "org", "organization",
               "location", "path", "category", "region")),
    ("kind", ("kind", "protocol", "proto", "transport", "connection", "connection type",
              "method", "scheme")),
    ("name", ("name", "session", "session name", "sessionname", "label", "title", "alias",
              "device", "device name", "display name", "hostname label")),
)


def _normalise_header(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_\-.]+", " ", (text or "").strip().lstrip("﻿").lower())).strip()


def _map_columns(header: list[str]) -> dict[str, int]:
    normalised = [_normalise_header(cell) for cell in header]
    mapping: dict[str, int] = {}
    claimed: set[int] = set()
    for field, aliases in _CSV_COLUMNS:
        for i, cell in enumerate(normalised):
            if i not in claimed and cell in aliases:
                mapping[field] = i
                claimed.add(i)
                break
    # Second pass for headers that only contain an alias ("mgmt ip address",
    # "primary ip v4"). "name" is matched last because it is a substring of
    # almost every other column heading.
    for field, aliases in _CSV_COLUMNS:
        if field in mapping:
            continue
        for i, cell in enumerate(normalised):
            if i in claimed:
                continue
            if any(len(a) >= 4 and a in cell for a in aliases):
                mapping[field] = i
                claimed.add(i)
                break
    return mapping


def parse_csv(content: str, filename: str = "") -> list[dict]:
    """Parse a CSV/TSV inventory, detecting the delimiter and the columns."""
    text = (content or "").lstrip("﻿")
    if not text.strip():
        return []
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any((c or "").strip() for c in r)]
    if not rows:
        return []

    columns = _map_columns(rows[0])
    if "host" not in columns and "name" not in columns:
        raise ValueError(
            "Could not find a host column. Give the CSV a header row naming at "
            "least one of: name, host, port, username, device_type, group."
        )

    def cell(row: list[str], field: str) -> str:
        i = columns.get(field, -1)
        return (row[i] or "").strip() if 0 <= i < len(row) else ""

    out: list[dict] = []
    for row in rows[1:]:
        host = cell(row, "host")
        name = cell(row, "name")
        # A one-column-per-device export often puts the FQDN under "name"; that
        # is still a reachable host, so use it rather than dropping the row.
        if not host:
            host = name
        if not host:
            continue
        kind = _PROTOCOLS.get(cell(row, "kind").lower(), "")
        port = cell(row, "port")
        if not kind:
            kind = "telnet" if _port(port, "ssh") == 23 else "ssh"
        out.append(
            _row(
                name=name or host,
                host=host,
                port=port,
                kind=kind,
                username=cell(row, "username"),
                device_type=cell(row, "device_type"),
                group=cell(row, "group"),
            )
        )
    return out


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------

def parse_nterm(content: str, filename: str = "") -> list[dict]:
    from . import exporters

    doc = exporters.parse_json(content)
    if not doc:
        raise ValueError("That file is not an NTerm export")
    if exporters.is_wrapped(doc):
        raise ValueError("Encrypted backup — enter the passphrase, then preview again")
    if not exporters.is_nterm_tree(doc):
        raise ValueError("That NTerm file is not a session tree")
    return exporters.tree_to_rows(doc)


_PARSERS = {
    "securecrt": parse_securecrt,
    "putty": parse_putty,
    "sshconfig": parse_ssh_config,
    "csv": parse_csv,
    "nterm": parse_nterm,
}

_FORMAT_ALIASES = {
    "crt": "securecrt",
    "secure_crt": "securecrt",
    "securecrt_ini": "securecrt",
    "ini": "securecrt",
    "reg": "putty",
    "registry": "putty",
    "putty_reg": "putty",
    "ssh": "sshconfig",
    "ssh_config": "sshconfig",
    "sshconf": "sshconfig",
    "openssh": "sshconfig",
    "config": "sshconfig",
    "nterm": "nterm",
    "json": "nterm",
}


def normalize_format(fmt: str) -> str:
    key = (fmt or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _FORMAT_ALIASES.get(key, key)


def detect(filename: str, content: str) -> str:
    """Guess the format of an uploaded inventory, or "unknown"."""
    head = (content or "")[:8192]
    lowered = head.lower()

    # Content signatures first: they are definitive, and an operator who saved
    # a PuTTY export as "sessions.txt" should still get the right parser.
    from . import exporters
    if exporters.parse_json(content or ""):
        return "nterm"
    if "simontatham" in lowered or "windows registry editor" in lowered or lowered.startswith("regedit4"):
        return "putty"
    if re.search(r'^\s*[A-Z]:"[^"]*"=', head, re.M):
        return "securecrt"
    if re.search(r"^\s*host\s+\S", head, re.M | re.I) and re.search(
        r"^\s*(hostname|identityfile|proxyjump|proxycommand|user|port|identitiesonly)\b", head, re.M | re.I
    ):
        return "sshconfig"

    name = (filename or "").strip().lower().replace("\\", "/")
    base = name.rsplit("/", 1)[-1]
    if base.endswith(".reg"):
        return "putty"
    if base.endswith(".ini"):
        return "securecrt"
    if base.endswith((".csv", ".tsv")):
        return "csv"
    if base in ("config", "ssh_config", "sshconfig") or base.endswith("/config"):
        return "sshconfig"

    first = next((line for line in head.splitlines() if line.strip()), "")
    if any(d in first for d in ",;\t|") and _map_columns(next(csv.reader(io.StringIO(first)), [])):
        return "csv"
    return "unknown"


def parse(content: str, fmt: str, filename: str = "") -> list[dict]:
    """Parse ``content`` with the named format, or "auto" to detect it."""
    key = normalize_format(fmt)
    if key in ("", "auto"):
        key = detect(filename, content)
    parser = _PARSERS.get(key)
    if parser is None:
        raise ValueError(
            f"Unsupported import format {fmt or 'auto'!r}. "
            f"Expected one of: {', '.join(FORMATS)}."
        )
    return parser(content, filename)
