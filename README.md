# NTerm

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**nterm.ai** — a network-engineer terminal for Cisco, Palo Alto, and Fortinet.

SecureCRT session vault. PuTTY-grade SSH. Warp-style AI. Built-in syslog, TFTP, and DHCP. Engineer bench feed from [nterm.ai](https://nterm.ai/bench-feed.json).

## Test locally (Docker)

Needs Docker Desktop (Mac/Windows) or Docker Engine (Linux).

```bash
git clone https://github.com/devnexthop/nterm.ai.git
cd nterm.ai
docker compose up --build
```

Open **http://localhost:8787**

First boot seeds a Lab customer (local shell + Cisco/PAN/Forti simulators). Session data lives in `./data` — treat it like a password database.

Stop with `Ctrl+C`, then `docker compose down`. Wipe the vault with `rm -rf data`.

### Lab toolkit ports (syslog / TFTP / DHCP)

```bash
docker compose -f docker-compose.yml -f docker-compose.lab.yml up --build
```

Maps UDP 514 / 69 / 67. Skip this until you point real gear at the box.

## Engineer bench feed

NTerm pulls cookbooks, runbooks, and lookups from **https://nterm.ai/bench-feed.json** (override with `NTERM_BENCH_URL`).

Host `site/bench-feed.json` on nterm.ai so that URL returns JSON. Contract: `GET /api/architect/example-feed`.

- Mode **merge** (default): remote overlays built-in
- If nterm.ai is unreachable, NTerm keeps the last cache, then falls back to built-in

Settings → Engineer bench feed → **Pull now**, or Bench → **Refresh feed**.

## Run without Docker

```bash
# engine
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload

# UI (another terminal)
cd frontend
npm install && npm run dev
```

Desktop window (dev — expects a running engine):

```bash
cd desktop
npm install
npm start
```

## Desktop app (Mac DMG / Windows EXE)

NTerm ships as a native app: Electron opens a window; a bundled Python engine runs locally on **127.0.0.1:8787**. No Docker required.

### Build (Mac)

Needs **Node.js 22+**, **Python 3.12** (PyInstaller does not support 3.14 yet), and **uv** recommended if Homebrew Python’s `venv` is broken:

```bash
git clone https://github.com/devnexthop/nterm.ai.git
cd nterm.ai
./scripts/package-desktop.sh
```

Output: `desktop/release/NTerm-0.1.0-mac-arm64.dmg` (and `.zip`).

Install: open the DMG, drag **NTerm** to Applications. The build is **unsigned** — first launch: right-click → **Open**, or `xattr -cr /Applications/NTerm.app`.

**Vault location (desktop):** `~/Library/Application Support/NTerm/data/` — separate from Docker’s `./data`. Back it up like a password database.

Stop Docker before launching the desktop app if it is using port 8787.

### Build (Windows)

Run on a Windows machine (PyInstaller bundles are OS-specific):

```bash
./scripts/package-desktop.sh
# or: cd desktop && npm run dist:win
```

Output: `desktop/release/NTerm-0.1.0-win-x64.exe` (NSIS installer).

Vault: `%APPDATA%\NTerm\data\`

## Keyboard

| Shortcut | Action |
| --- | --- |
| `Ctrl/Cmd+K` | Command palette |
| `Ctrl/Cmd+N` | New session |
| `Ctrl/Cmd+B` | Broadcast bar |
| `Ctrl/Cmd+Shift+A` | Toggle AI |

## Deploying

See **[DEPLOY.md](DEPLOY.md)**. Short version: `docker compose up -d --build`, then
http://localhost:8787. The compose file binds to **loopback only**. NTerm does hold a
per-install API token, but it guards against hostile websites, not against network reach —
so do not expose the port directly.

## Contributing

See **[CONTRIBUTING.md](CONTRIBUTING.md)**. Security issues go to
**[SECURITY.md](SECURITY.md)**, never a public issue.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Copyright 2026 ValeronLabs LLC.
