PROFILES = {
    "generic": {
        "label": "Generic SSH",
        "paging": [],
        "dialect": "generic unix / network device",
    },
    "cisco_ios": {
        "label": "Cisco IOS / IOS-XE",
        "paging": ["terminal length 0", "terminal width 0"],
        "dialect": "Cisco IOS / IOS-XE",
    },
    "cisco_nxos": {
        "label": "Cisco NX-OS",
        "paging": ["terminal length 0", "terminal width 0"],
        "dialect": "Cisco NX-OS",
    },
    "cisco_asa": {
        "label": "Cisco ASA / FTD",
        "paging": ["terminal pager 0"],
        "dialect": "Cisco ASA",
    },
    "paloalto": {
        "label": "Palo Alto PAN-OS",
        "paging": ["set cli pager off", "set cli scripting-mode on"],
        "dialect": "Palo Alto PAN-OS",
    },
    "fortinet": {
        "label": "Fortinet FortiOS",
        "paging": ["config system console", "set output standard", "end"],
        "dialect": "Fortinet FortiOS",
    },
    "juniper": {
        "label": "Juniper Junos",
        "paging": ["set cli screen-length 0", "set cli screen-width 0"],
        "dialect": "Juniper Junos",
    },
    "linux": {
        "label": "Linux / Unix",
        "paging": [],
        "dialect": "Linux shell",
    },
    "windows": {
        "label": "Windows / PowerShell",
        "paging": [],
        "dialect": "Windows PowerShell",
    },
}


# SSH algorithm preference: modern first so OpenSSH 9 / current PAN / Forti
# pick ChaCha/GCM/curve25519, then the suites old IOS 12 / ASA 8 / early
# PAN-OS still require. asyncssh 2.21 *supports* the legacy names but does
# not offer CBC, 3DES, DH-group1, group-exchange-sha1, or ssh-dss by default
# — so a 15-year-old core never matches unless we send them.
#
# RC4 (arcfour*) is omitted on purpose. GSS/Kerberos kex is omitted so a
# box that does not speak it does not stall in negotiation.

_SSH_PREFERRED = {
    "encryption_algs": [
        "chacha20-poly1305@openssh.com",
        "aes256-gcm@openssh.com",
        "aes128-gcm@openssh.com",
        "aes256-ctr",
        "aes192-ctr",
        "aes128-ctr",
        "aes256-cbc",
        "aes192-cbc",
        "aes128-cbc",
        "3des-cbc",
        "blowfish-cbc",
    ],
    "kex_algs": [
        "curve25519-sha256",
        "curve25519-sha256@libssh.org",
        "curve448-sha512",
        "ecdh-sha2-nistp521",
        "ecdh-sha2-nistp384",
        "ecdh-sha2-nistp256",
        "diffie-hellman-group16-sha512",
        "diffie-hellman-group18-sha512",
        "diffie-hellman-group14-sha256",
        "diffie-hellman-group-exchange-sha256",
        "diffie-hellman-group14-sha1",
        "diffie-hellman-group-exchange-sha1",
        "diffie-hellman-group1-sha1",
    ],
    "mac_algs": [
        "hmac-sha2-256-etm@openssh.com",
        "hmac-sha2-512-etm@openssh.com",
        "umac-128-etm@openssh.com",
        "hmac-sha1-etm@openssh.com",
        "hmac-sha2-256",
        "hmac-sha2-512",
        "hmac-sha1",
        "hmac-sha1-96",
        "hmac-md5",
        "hmac-md5-96",
    ],
    "server_host_key_algs": [
        "ssh-ed25519",
        "ssh-ed448",
        "ecdsa-sha2-nistp256",
        "ecdsa-sha2-nistp384",
        "ecdsa-sha2-nistp521",
        "rsa-sha2-256",
        "rsa-sha2-512",
        "ssh-rsa",
        "ssh-dss",
    ],
    "signature_algs": [
        "ssh-ed25519",
        "rsa-sha2-256",
        "rsa-sha2-512",
        "ecdsa-sha2-nistp256",
        "ssh-rsa",
        "ssh-dss",
    ],
}


def _asyncssh_available() -> dict[str, set[str]]:
    from asyncssh.encryption import get_encryption_algs
    from asyncssh.kex import get_kex_algs
    from asyncssh.mac import get_mac_algs
    from asyncssh.public_key import get_public_key_algs

    def names(raw) -> set[str]:
        return {a.decode() if isinstance(a, bytes) else str(a) for a in raw}

    host = names(get_public_key_algs())
    return {
        "encryption_algs": names(get_encryption_algs()),
        "kex_algs": names(get_kex_algs()),
        "mac_algs": names(get_mac_algs()),
        "server_host_key_algs": host,
        "signature_algs": host,
    }


def ssh_connect_kwargs() -> dict[str, list[str]]:
    """asyncssh.connect kwargs: preferred ∩ actually implemented."""
    have = _asyncssh_available()
    out: dict[str, list[str]] = {}
    for key, preferred in _SSH_PREFERRED.items():
        picked = [a for a in preferred if a in have.get(key, set())]
        if picked:
            out[key] = picked
    return out


def ssh_hostkey_kwargs() -> dict[str, list[str]]:
    """get_server_host_key only accepts kex + host-key lists."""
    full = ssh_connect_kwargs()
    return {
        "kex_algs": full["kex_algs"],
        "server_host_key_algs": full["server_host_key_algs"],
    }


# Kept for callers/tests that still import the raw preference table.
SSH_ALGORITHMS = ssh_connect_kwargs()
