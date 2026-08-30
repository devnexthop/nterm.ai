"""SSH algorithm lists: modern first, legacy still offered.

asyncssh 2.21 supports CBC / 3DES / DH-group1 / ssh-dss but does not
advertise them by default. Old IOS / ASA never match unless we send them.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.device_profiles import _SSH_PREFERRED, _asyncssh_available, ssh_connect_kwargs, ssh_hostkey_kwargs

LEGACY = (
    "aes128-cbc",
    "3des-cbc",
    "diffie-hellman-group1-sha1",
    "diffie-hellman-group-exchange-sha1",
    "ssh-dss",
    "hmac-sha1",
)
MODERN = (
    "chacha20-poly1305@openssh.com",
    "aes256-gcm@openssh.com",
    "curve25519-sha256",
    "rsa-sha2-512",
    "ssh-ed25519",
)


def _flat(kw: dict[str, list[str]]) -> set[str]:
    names: set[str] = set()
    for v in kw.values():
        names.update(v)
    return names


def test_advertised_names_exist_in_asyncssh():
    have = _asyncssh_available()
    kw = ssh_connect_kwargs()
    for key, algs in kw.items():
        assert algs, key
        extra = set(algs) - have[key]
        assert not extra, extra


def test_legacy_and_modern_offered_when_asyncssh_implements_them():
    have = _asyncssh_available()
    names = _flat(ssh_connect_kwargs())
    implemented = set()
    for bucket in have.values():
        implemented |= bucket
    for alg in (*LEGACY, *MODERN):
        if alg in implemented:
            assert alg in names, alg


def test_modern_encryption_sorts_before_cbc():
    enc = ssh_connect_kwargs()["encryption_algs"]
    assert "chacha20-poly1305@openssh.com" in enc
    assert "aes128-cbc" in enc
    assert enc.index("chacha20-poly1305@openssh.com") < enc.index("aes128-cbc")
    assert enc.index("aes128-ctr") < enc.index("3des-cbc")


def test_hostkey_probe_includes_legacy_kex_and_dss():
    probe = ssh_hostkey_kwargs()
    assert "kex_algs" in probe and "server_host_key_algs" in probe
    assert "encryption_algs" not in probe
    kex = probe["kex_algs"]
    assert "diffie-hellman-group1-sha1" in kex
    assert "diffie-hellman-group-exchange-sha1" in kex
    assert kex.index("curve25519-sha256") < kex.index("diffie-hellman-group1-sha1")
    assert "ssh-dss" in probe["server_host_key_algs"]


def test_rc4_and_gss_are_not_on_the_preference_list():
    blob = " ".join(a for v in _SSH_PREFERRED.values() for a in v)
    assert "arcfour" not in blob
    assert "gss-" not in blob
