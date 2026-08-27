"""Native session-tree export / vault wrap."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import exporters


def test_structure_has_no_secrets():
    class Sess:
        name = "sw1"
        kind = "ssh"
        device_type = "cisco_ios"
        host = "10.0.0.1"
        port = 22
        username = "cisco"
        jump_host = ""
        notes = ""
        logging_enabled = True
        post_login = ""
        folder = "Plant"
        baud = 9600
        password_enc = "should-not-appear"
        enable_password_enc = None
        private_key_enc = None

    class Cust:
        name = "Acme"
        color = "#ffb020"
        notes = ""
        sessions = [Sess()]

    tree = exporters.build_tree([Cust()], vault=False)
    assert tree["kind"] == "structure"
    assert tree["nterm_export"] == 1
    body = tree["customers"][0]["sessions"][0]
    assert body["folder"] == "Plant"
    assert "password" not in body


def test_wrap_roundtrip():
    tree = {
        "nterm_export": 1,
        "kind": "vault",
        "customers": [{"name": "A", "color": "#fff", "notes": "", "sessions": []}],
    }
    wrapped = exporters.wrap_vault(tree, "correct-horse")
    assert wrapped["kind"] == "vault-wrapped"
    out = exporters.unwrap_vault(wrapped, "correct-horse")
    assert out["kind"] == "vault"


def test_wrong_passphrase_fails():
    tree = {
        "nterm_export": 1,
        "kind": "vault",
        "customers": [{"name": "A", "color": "#fff", "notes": "", "sessions": []}],
    }
    wrapped = exporters.wrap_vault(tree, "correct-horse")
    try:
        exporters.unwrap_vault(wrapped, "wrong-pass")
        assert False, "should have failed"
    except ValueError as exc:
        assert "Wrong passphrase" in str(exc)


def test_short_passphrase_rejected():
    try:
        exporters.wrap_vault({"nterm_export": 1, "kind": "vault", "customers": []}, "short")
        assert False
    except ValueError:
        pass


def test_tree_to_rows_keeps_folder():
    tree = {
        "nterm_export": 1,
        "kind": "structure",
        "customers": [{
            "name": "Acme",
            "color": "#fff",
            "sessions": [{"name": "sw1", "host": "10.0.0.1", "folder": "Plant/IDF"}],
        }],
    }
    rows = exporters.tree_to_rows(tree)
    assert rows[0]["folder"] == "Plant/IDF"
    assert rows[0]["customer_name"] == "Acme"
