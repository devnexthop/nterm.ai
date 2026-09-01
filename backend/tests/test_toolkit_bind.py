import errno

from app.toolkit.bindutil import explain_bind_error, exposure


def test_address_in_use_is_explicit():
    err = OSError(errno.EADDRINUSE, "Address already in use")
    msg = explain_bind_error(err, name="Syslog", port=514)
    assert "514" in msg
    assert "already in use" in msg
    assert "was not started" in msg


def test_permission_denied_mentions_root_or_high_port():
    err = OSError(errno.EACCES, "Permission denied")
    msg = explain_bind_error(err, name="TFTP", port=69)
    assert "69" in msg
    assert "permission denied" in msg.lower()


def test_exposure_native_when_not_in_docker(monkeypatch):
    monkeypatch.setattr("app.toolkit.bindutil.in_container", lambda: False)
    monkeypatch.setattr("app.toolkit.bindutil.lab_ports_published", lambda: False)
    exp = exposure()
    assert exp["mode"] == "native"
    assert exp["host_ports"] is True


def test_exposure_container_without_lab_ports(monkeypatch):
    monkeypatch.setattr("app.toolkit.bindutil.in_container", lambda: True)
    monkeypatch.setattr("app.toolkit.bindutil.lab_ports_published", lambda: False)
    exp = exposure()
    assert exp["mode"] == "container"
    assert exp["host_ports"] is False
