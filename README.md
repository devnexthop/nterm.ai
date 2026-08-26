# NTerm

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

Desktop window:

```bash
cd desktop
npm install
npm start
```

Installers (Windows EXE / Mac DMG) come later. Local test is Docker.

## Keyboard

| Shortcut | Action |
| --- | --- |
| `Ctrl/Cmd+K` | Command palette |
| `Ctrl/Cmd+N` | New session |
| `Ctrl/Cmd+B` | Broadcast bar |
| `Ctrl/Cmd+Shift+A` | Toggle AI |
