"""Host-key TOFU store.

The property that matters: a key that CHANGES is refused. First contact is
recorded (documented limitation: auto-accepted, not prompted).
"""
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def hk(tmp_path, monkeypatch):
    monkeypatch.setenv("NTERM_DATA_DIR", str(tmp_path))
    for mod in ("app.config", "app.hostkeys"):
        sys.modules.pop(mod, None)
    import app.hostkeys as hostkeys
    importlib.reload(hostkeys)
    return hostkeys


KEY_A = b"\x00\x01ssh-rsa-key-material-A"
KEY_B = b"\x00\x02ssh-rsa-key-material-B"


def test_first_contact_is_recorded_and_reported_as_new(hk):
    fp, first = hk.check_and_record("10.0.0.1", 22, KEY_A, "ssh-rsa")
    assert first is True
    assert fp.startswith("SHA256:")


def test_same_key_on_reconnect_is_not_flagged_as_new(hk):
    fp1, _ = hk.check_and_record("10.0.0.1", 22, KEY_A, "ssh-rsa")
    fp2, first = hk.check_and_record("10.0.0.1", 22, KEY_A, "ssh-rsa")
    assert first is False
    assert fp1 == fp2


def test_changed_key_is_REFUSED(hk):
    """The core control. A different key on a known host must not connect."""
    hk.check_and_record("10.0.0.1", 22, KEY_A, "ssh-rsa")
    with pytest.raises(hk.HostKeyChanged) as exc:
        hk.check_and_record("10.0.0.1", 22, KEY_B, "ssh-rsa")
    assert exc.value.old_fp != exc.value.new_fp
    assert "CHANGED" in str(exc.value)


def test_same_host_different_port_is_a_separate_identity(hk):
    hk.check_and_record("10.0.0.1", 22, KEY_A, "ssh-rsa")
    _, first = hk.check_and_record("10.0.0.1", 2222, KEY_B, "ssh-rsa")
    assert first is True  # not a mismatch — different endpoint


def test_forget_allows_repinning_after_a_legitimate_rebuild(hk):
    hk.check_and_record("10.0.0.1", 22, KEY_A, "ssh-rsa")
    assert hk.forget("10.0.0.1:22") is True
    _, first = hk.check_and_record("10.0.0.1", 22, KEY_B, "ssh-rsa")
    assert first is True


def test_forget_unknown_host_returns_false(hk):
    assert hk.forget("192.0.2.9:22") is False


def test_fingerprint_is_openssh_sha256_format(hk):
    fp = hk.fingerprint(KEY_A)
    assert fp.startswith("SHA256:")
    assert "=" not in fp  # base64 padding stripped, as OpenSSH does


def test_store_survives_reload(hk):
    hk.check_and_record("10.0.0.1", 22, KEY_A, "ssh-rsa")
    importlib.reload(hk)
    assert hk.get("10.0.0.1", 22)["fingerprint"] == hk.fingerprint(KEY_A)


def test_list_all_reports_pinned_hosts(hk):
    hk.check_and_record("10.0.0.1", 22, KEY_A, "ssh-rsa")
    hk.check_and_record("10.0.0.2", 22, KEY_B, "ssh-rsa")
    entries = hk.list_all()
    assert {e["host_port"] for e in entries} == {"10.0.0.1:22", "10.0.0.2:22"}
