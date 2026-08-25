# NTerm

**nterm.ai** — a downloadable network-engineer terminal for **Windows** and **Mac**.

SecureCRT session vault. PuTTY-grade SSH to Cisco, Palo Alto, Fortinet. Warp-style AI. Built-in Kiwi / TFTPD32 tools (syslog, TFTP, DHCP). Themes, config analyzers, extensions.

## Install (the actual app)

### Windows
1. Download **NTerm Setup.exe** from [nterm.ai](https://nterm.ai) (or a GitHub Release).
2. Run the installer. Shortcuts go on the Desktop and Start Menu.
3. Launch **NTerm**. The engine binds to `127.0.0.1` only.

### Mac
1. Download **NTerm.dmg**.
2. Drag **NTerm** into Applications.
3. First launch: System Settings → Privacy & Security → Open Anyway (until you notarize with an Apple Developer ID).

Installers are produced by GitHub Actions (Windows + macOS + Linux) when you push a `v*` tag, or by:

```bash
# on the target OS
cd relay
./scripts/package-desktop.sh
# → desktop/release/
```

### Point nterm.ai at downloads

Host `relay/site/` on Cloudflare Pages (or any static host) for the domain you own. Put release binaries in `site/download/`:

- `NTerm-Setup.exe`
- `NTerm.dmg`

## Run in development

```bash
# engine
cd relay/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload

# UI
cd relay/frontend
npm install && npm run dev
```

Desktop window (uses the engine if it is already up):

```bash
cd relay/desktop
npm install
npm start
```

Docker (lab / toolkit ports):

```bash
cd relay && docker compose up --build
```

## Engineer bench feed (your server)

NTerm can pull cookbooks, runbooks, and lookups from NextHop’s API.

1. Host JSON that matches `GET /api/architect/example-feed` (copy `site/bench-feed.json` to start).
2. Suggested URLs:
   - `https://nexthopllc.com/api/nterm/bench.json`
   - `https://nterm.ai/bench-feed.json`
3. In NTerm → Settings → **Engineer bench feed**, paste the URL. Optional Bearer / `X-NTerm-Key`.
4. Mode: **merge** (remote overlays built-in), **remote** only, or **local** only.
5. **Pull now** on Settings or **Refresh feed** on Bench.

```http
GET /api/nterm/bench.json
Authorization: Bearer <optional>
X-NTerm-Key: <optional>
```

If your server is down, NTerm keeps the last cache, then falls back to built-in.

## Brand

- Name: **NTerm**
- Domain: **nterm.ai**
- Mark: amber **N** with a terminal block cursor on navy
- Files: `branding/nterm-app-icon.png`, `branding/nterm-wordmark.png`

## Keyboard

| Shortcut | Action |
| --- | --- |
| `Ctrl/Cmd+K` | Command palette |
| `Ctrl/Cmd+N` | New session |
| `Ctrl/Cmd+B` | Broadcast bar |
| `Ctrl/Cmd+Shift+A` | Toggle AI |

## Security

Passwords are Fernet-encrypted under the OS user data directory (`%APPDATA%\NTerm` / `~/Library/Application Support/NTerm`). Treat that folder like a password database.
