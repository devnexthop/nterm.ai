# Security Policy

NTerm stores credentials. Please treat vulnerabilities here as high-impact.

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Report privately via one of:

- GitHub private vulnerability reporting — the **Security** tab → *Report a vulnerability*
- Email **security@nterm.ai**

Please include what you can: affected version (`/api/health` reports it), a description,
reproduction steps, and impact. We aim to acknowledge within **3 business days** and to
ship a fix or a mitigation plan within **30 days** for confirmed issues.

We will credit you in the release notes unless you ask us not to.

## Scope

In scope: this repository — the FastAPI backend, the web frontend, the Electron shell,
and the Docker packaging.

Out of scope: the marketing site, the session-sharing relay service, and third-party
dependencies (report those upstream, then tell us so we can pin around it).

## What NTerm holds

Anyone assessing NTerm should know where the sensitive material lives:

| Where | What |
|---|---|
| `./data` (bind-mounted to `/data`) | session hosts, usernames, stored credentials, SSH host keys |
| Settings | AI provider API key, bench feed key, relay token — encrypted at rest |
| Terminal scrollback | whatever the device printed, including secrets you typed |

`./data` is a credential vault. It is gitignored and must stay that way. `rm -rf data`
is unrecoverable.

## Known posture

- **Session sharing redacts by pattern, not by guarantee.** The relay strips known secret
  shapes before viewers see them. That is pattern matching. Treat a shared session as visible.
- **NTerm runs commands on network devices.** AI-proposed commands are never sent without an
  explicit confirm. If you find a path that bypasses that confirmation, it is a security bug —
  report it.
