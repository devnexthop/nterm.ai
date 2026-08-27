# Changelog

All notable changes to NTerm. This project follows [Semantic Versioning](https://semver.org/).

The version you are running is shown in **Settings → About** and at `/api/health`.
Both report the release number *and* the exact commit it was built from, so
"which build is this?" always has an answer.

## [0.2.0] — 2026-08-27

The first release under Apache-2.0.

### Added
- **Apache-2.0 licence.** NTerm previously shipped with no `LICENSE` file, which
  legally meant all rights reserved — nobody who cloned it could use it.
- **Safe-write pipeline.** A drafted change is now checked by a per-vendor,
  default-deny policy gate and rehearsed against the built-in simulator before
  the operator is asked to confirm it. A blocked draft cannot be sent.
  Covers Cisco IOS/NX-OS/IOS-XR, Junos, Arista EOS, PAN-OS and FortiOS.
- **Windows PowerShell local shell** over ConPTY.
- **Session import** from SecureCRT, PuTTY, `ssh_config` and CSV. Structure
  only — stored passwords are never read out of another tool's files.
- **Credentials management** in Settings: reuse one username and password
  across many devices.
- **Session logging** is switchable, and the log location is stated plainly.
- **Selectable terminal typeface** — seven monospace faces.
- **AI in the editor**: Explain, Comment, Tidy, Review and Convert-to-vendor,
  acting on the buffer with an undo, rather than only in the chat panel.
- **Network toolkit in the container**: `ip`, `ping`, `traceroute`, `dig`,
  `nc`, `ss`, `curl`, `telnet`, `tcpdump`, `mtr`, `socat`, `less`, `nano`, `vi`.
- **Update check** in Settings → About. Manual only; NTerm does not phone home.
- `SECURITY.md`, `CONTRIBUTING.md`, `DEPLOY.md` and issue templates.

### Changed
- **Rebuilt the window.** Navigation moved to a left rail; the top row became a
  session header carrying only active-session concerns. Merge/Split/Quad became
  a segmented control beside the tabs it acts on. The Do bar, chip bar and
  broadcast row collapsed into one command bar with Do / Cast / Macros modes.
  Thirteen chrome buttons became four; four stacked bars became one.
- **Chips are now Macros.**
- **Nine terminal themes get live previews.** You could not previously see a
  theme without applying it. New default: **Valeron**.
- The Do bar now detects the session's userland — Linux (GNU), macOS (BSD) and
  Windows PowerShell — and drafts in the right dialect. It is useful as a
  general terminal assistant, not only against network gear.
- The bench feed uses conditional requests and backs off on 429/503.
- Docker images are stamped with the git commit they were built from.

### Fixed
- **`set Loopback0 to 1.1.1.1/24` drafted `ip address 1.1.1.0`** — the network
  address rather than the host address you asked for. Routes and DHCP scopes
  correctly still use the network address.
- **The backend would not start on Windows at all**: `pty`, `termios` and
  `fcntl` were imported at module level.
- **A crash in one terminal pane took down the whole app** and every other open
  session. Each pane is now isolated.
- The Dockerfile advertised a licence — `LicenseRef-NTerm-Source-Available` —
  that existed nowhere in the repository.
- `Monitor` was a complete page with no way to reach it.

## [0.1.0] — 2026-08

Initial beta. Sessions over SSH, Serial, Telnet and local shell; per-customer
credential vault; broadcast; syslog/TFTP/DHCP toolkit; offline Cisco, PAN-OS and
FortiOS simulators; MCP server and client.
