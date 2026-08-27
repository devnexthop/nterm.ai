"""Rehearse a drafted change against the built-in simulator before it is shown.

The stage nobody else has: run the draft somewhere harmless first, so a syntax
error surfaces before the operator is asked to approve it.

The hard constraint is honesty about coverage. The simulators are stubs — they
model the `show` surface and a handful of config verbs, and answer anything else
with "unknown command or simulator stub". A rehearsal that reported those as
failures would flag almost every legitimate config line, and a check that cries
wolf is worse than no check: people learn to click past it, exactly like a
confirmation dialog nobody reads.

So the result is three-state, never two:

    pass     the simulator executed it and did not object
    unknown  the simulator has no opinion — NOT a failure, and never shown as one
    fail     the simulator actively rejected it

Only `fail` is evidence. `unknown` is the honest answer for a stub, and the
proportion of `unknown` is reported so the UI can say how much of the draft was
actually exercised rather than implying full coverage.
"""
from __future__ import annotations

import re

from ..simulators import DeviceSimulator

# The simulator's own "I don't model this" replies. These mean no coverage.
_STUB = re.compile(
    r"(unknown command or simulator stub|unknown command:|unknown action)",
    re.I,
)

# Real rejections a device would also give. Deliberately narrow — anything we
# are unsure about must fall through to `unknown`, never to `fail`.
_REJECT = [
    (re.compile(r"%\s*invalid input", re.I), "invalid input"),
    (re.compile(r"%\s*incomplete command", re.I), "incomplete command"),
    (re.compile(r"%\s*ambiguous command", re.I), "ambiguous command"),
    (re.compile(r"%\s*privileged command", re.I), "needs a higher privilege level"),
    (re.compile(r"command parse error", re.I), "parse error"),
    (re.compile(r"\bcommand fail\b", re.I), "command failed"),
    (re.compile(r"invalid syntax", re.I), "invalid syntax"),
]

_SUPPORTED = ("cisco", "paloalto", "fortinet")

# The simulator prints its banner on the first real input. Left unhandled that
# banner lands on line one of every draft and reads as a clean pass — a false
# negative on the very first command, which is the worst place to have one.
_BANNER = re.compile(r"NTerm simulator", re.I)


def _prime(sim: DeviceSimulator) -> None:
    """Drive the simulator's login state machine so the first drafted command
    reaches the command handler rather than being eaten as a username.

    The simulator starts in `login`, takes a username, then a password, and only
    then prints its banner and dispatches. Priming on output alone is fragile —
    the `Password:` reply carries no banner and looks finished — so this drives
    it off the mode field and asserts it actually got there.
    """
    for _ in range(6):
        if getattr(sim, "mode", "") not in ("login", "password"):
            break
        sim.feed("nterm\n")

    # Start from the privilege level a real session would already be at.
    # Without this, `configure terminal` rehearses as "needs a higher privilege
    # level" — an artefact of the rehearsal, not a defect in the draft, and
    # exactly the kind of false failure this module exists to avoid.
    if (sim.device_type or "").startswith("cisco"):
        sim.feed("enable\n")
        if getattr(sim, "mode", "") == "password":
            sim.feed("nterm\n")


def supported(device_type: str | None) -> bool:
    dt = (device_type or "").lower()
    return any(dt.startswith(p) or dt == p for p in _SUPPORTED)


def _verdict_for(output: str) -> tuple[str, str]:
    if _BANNER.search(output):
        # Banner instead of a reply means the simulator never judged this line.
        return "unknown", "simulator returned its banner, not a verdict"
    if _STUB.search(output):
        return "unknown", "simulator does not model this command"
    for rx, why in _REJECT:
        if rx.search(output):
            return "fail", why
    return "pass", ""


def dry_run(commands: list[str], device_type: str, hostname: str = "rehearsal") -> dict:
    """Feed a draft to a throwaway simulator and report what it made of it."""
    if not commands:
        return {"ran": False, "reason": "nothing to rehearse"}
    if not supported(device_type):
        return {"ran": False, "reason": f"no simulator for {device_type or 'this platform'}"}

    sim = DeviceSimulator(device_type, hostname)
    _prime(sim)

    steps: list[dict] = []
    for raw in commands:
        line = raw.strip()
        if not line:
            continue
        try:
            out = sim.feed(line + "\n")
        except Exception as exc:  # a simulator bug must not break drafting
            steps.append({"command": line, "verdict": "unknown", "detail": f"simulator error: {exc}"})
            continue
        # Drop the echoed command and the trailing prompt before judging.
        body = out.replace(line, "", 1)
        verdict, detail = _verdict_for(body)
        steps.append({"command": line, "verdict": verdict, "detail": detail})

    failures = [s for s in steps if s["verdict"] == "fail"]
    covered = sum(1 for s in steps if s["verdict"] != "unknown")
    return {
        "ran": True,
        "device_type": device_type,
        "steps": steps,
        "failures": [f"{s['command']} — {s['detail']}" for s in failures],
        "covered": covered,
        "total": len(steps),
        # Stated plainly so the UI never implies more assurance than there is.
        "coverage_note": (
            f"{covered} of {len(steps)} lines were actually exercised; "
            "the rest are not modelled by the simulator"
            if covered < len(steps) else "every line was exercised"
        ),
        "ok": not failures,
    }


if __name__ == "__main__":
    checks = [
        (["configure terminal", "interface Loopback0", " ip address 1.1.1.1 255.255.255.0"], "cisco_ios"),
        (["show ip interface brief"], "cisco_ios"),
        (["wibble frobnicate"], "cisco_ios"),
        (["show interface"], "paloalto"),
        (["get system status"], "fortinet"),
        (["set foo"], "juniper"),
    ]
    for cmds, dt in checks:
        r = dry_run(cmds, dt)
        if not r["ran"]:
            print(f"{dt:10} skipped   — {r['reason']}")
            continue
        print(f"{dt:10} ok={str(r['ok']):5} covered={r['covered']}/{r['total']}  {r['coverage_note']}")
        for s in r["steps"]:
            print(f"    {s['verdict']:7} {s['command'][:44]:46} {s['detail']}")
    # The invariant that matters: a stub reply must never become a failure.
    r = dry_run(["interface Loopback0"], "cisco_ios")
    assert r["ok"] is True, "stub replies must not be reported as failures"
    assert r["steps"][0]["verdict"] == "unknown"
    print("\ninvariant held: simulator stubs are 'unknown', never 'fail'")
