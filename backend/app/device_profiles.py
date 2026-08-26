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


# asyncssh options that older Cisco / PAN / Forti boxes still require
SSH_ALGORITHMS = {
    "encryption_algs": [
        "aes128-ctr",
        "aes256-ctr",
        "aes192-ctr",
        "aes128-gcm@openssh.com",
        "aes256-gcm@openssh.com",
        "aes128-cbc",
        "aes256-cbc",
        "3des-cbc",
    ],
    "kex_algs": [
        "curve25519-sha256",
        "ecdh-sha2-nistp256",
        "ecdh-sha2-nistp384",
        "diffie-hellman-group14-sha256",
        "diffie-hellman-group14-sha1",
        "diffie-hellman-group-exchange-sha256",
        "diffie-hellman-group1-sha1",
    ],
    "mac_algs": [
        "hmac-sha2-256",
        "hmac-sha2-512",
        "hmac-sha1",
    ],
    "server_host_key_algs": [
        "ssh-ed25519",
        "ecdsa-sha2-nistp256",
        "rsa-sha2-256",
        "rsa-sha2-512",
        "ssh-rsa",
    ],
}
