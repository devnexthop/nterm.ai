# Deploying NTerm

**Docker** is the default for server-style runs. **Native installers** (Mac DMG, Windows EXE) are built from the same repo — see [Desktop app](#desktop-app) below.

## Quick start (Docker)

```bash
git clone https://github.com/devnexthop/nterm.ai.git
cd nterm.ai
docker compose up -d --build
```

Open **http://localhost:8787**.

First boot seeds a **Lab** customer with a local shell and Cisco/PAN/Forti simulators, so
you can try everything without touching real gear.

## What you get

| | |
|---|---|
| Image | `nterm:local`, built from the repo `Dockerfile` |
| Port | `127.0.0.1:8787` — **loopback only** by default |
| Data | `./data` bind-mounted to `/data` |
| Health | `GET /api/health` |

## `./data` is a credential vault

It holds session hosts, usernames, stored credentials and SSH host keys. Back it up like a
password database, and never commit it.

```bash
docker compose down
tar czf nterm-data-$(date +%F).tar.gz data/
```

`rm -rf data` is unrecoverable. Deleting it wipes every saved session and credential.

## Bind address — read before exposing it

The compose file publishes to `127.0.0.1` on purpose.

NTerm generates a **per-install API token** (`./data/.auth_token`, mode 0600) and requires it
on every `/api`, `/ws` and `/mcp` request. That exists to stop a malicious website reaching
`127.0.0.1:8787` from your browser — CORS alone does not block a `no-cors` POST.

**It is not a network access control.** `/` itself is unguarded, because the SPA has to load
before it can present a token — so anything that can reach the port can fetch the page and
read the token straight out of the meta tag. Binding to loopback is what actually protects
the vault.

Do not change the mapping to `0.0.0.0:8787` on a shared or internet-facing host. If you need
remote access, put it behind something that authenticates:

```bash
# preferred: don't expose it at all, tunnel instead
ssh -N -L 8787:127.0.0.1:8787 you@the-host
```

Otherwise terminate TLS and enforce auth at a reverse proxy (Caddy, nginx, Traefik) and keep
the container bound to loopback.

## Lab toolkit (syslog / TFTP / DHCP)

These bind privileged UDP ports (514, 69, 67). Only start this profile when real gear is
pointed at the box:

```bash
docker compose -f docker-compose.yml -f docker-compose.lab.yml up -d --build
```

## Configuration

| Variable | Default | What |
|---|---|---|
| `NTERM_DATA_DIR` | `/data` | Vault location inside the container |
| `NTERM_BENCH_URL` | `https://nterm.ai/bench-feed.json` | Engineer bench feed |
| `NTERM_BUILD_SHA` | `dev` | Build stamp shown in Settings → About |
| `NTERM_AUTH_TOKEN` | generated | Override the per-install API token (useful for scripted access) |

AI provider keys, the bench key and the relay token are **not** environment variables — set
them in **Settings**, where they are encrypted into the vault.

## Upgrading

```bash
git pull
docker compose up -d --build
```

`./data` survives. Check **Settings → About** for the running version, or:

```bash
curl -s localhost:8787/api/health
```

## Operating

```bash
docker compose logs -f nterm     # logs
docker compose restart nterm     # restart
docker compose down              # stop, keeps ./data
docker compose ps                # health status
```

## Build for another architecture

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  --build-arg GIT_SHA=$(git rev-parse --short HEAD) \
  -t nterm:$(cat VERSION) .
```

## Troubleshooting

| Symptom | Cause |
|---|---|
| Port 8787 in use | Another NTerm is running — `docker compose ps` |
| Container unhealthy | `docker compose logs nterm`; the healthcheck polls `/api/health` |
| Sessions vanished | `./data` was deleted or not mounted — check the compose `volumes:` |
| Share button disabled | No relay token. Settings → Sharing |
| Bench feed won't pull | Settings → Bench → Pull now reports the reason; NTerm falls back to built-in |

## Desktop app

Electron shell + PyInstaller-bundled engine. Binds **127.0.0.1:8787** only. Credential vault is per-user, not `./data` in the repo.

| OS | Vault path |
|---|---|
| macOS | `~/Library/Application Support/NTerm/data/` |
| Windows | `%APPDATA%\NTerm\data\` |
| Linux (dev) | `~/.nterm/` |

### Build Mac DMG

From repo root on macOS:

```bash
./scripts/package-desktop.sh
```

Prerequisites: Node.js 22+, Python 3.12 (not 3.14 — PyInstaller pin), Xcode CLT. If `python3 -m venv` fails (Homebrew expat issue), install [uv](https://github.com/astral-sh/uv) — the script uses it automatically.

Artifacts: `desktop/release/NTerm-<version>-mac-arm64.dmg`

First launch of an unsigned build: right-click **NTerm.app** → **Open**, or `xattr -cr /Applications/NTerm.app`.

### Build Windows EXE

Must run **on Windows** (cannot cross-compile the Python engine from Mac):

```bash
./scripts/package-desktop.sh
```

Artifact: `desktop/release/NTerm-<version>-win-x64.exe`

### Desktop troubleshooting

| Symptom | Cause |
|---|---|
| Port 8787 in use | Docker NTerm or dev server still running — stop it before launching the app |
| "NTerm failed to start" | Engine did not reach `/api/health` in time — check Console or run `nterm-engine` from `NTerm.app/Contents/Resources/engine/` |
| Gatekeeper blocks app | Unsigned build — use right-click Open or `xattr -cr` |
| Empty vault after switching from Docker | Desktop and Docker use different vault paths (by design) |
