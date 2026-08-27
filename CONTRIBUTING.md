# Contributing to NTerm

Thanks for looking. NTerm is Apache-2.0 and contributions are welcome.

## Before you start

- **Bugs and features** — open an issue first for anything non-trivial, so we can agree on
  the shape before you spend time.
- **Security** — do not open an issue. See [SECURITY.md](SECURITY.md).

## Run it locally

```bash
git clone https://github.com/devnexthop/nterm.ai.git
cd nterm.ai
docker compose up --build      # http://localhost:8787
```

Without Docker:

```bash
# backend
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload

# frontend, in another shell
cd frontend && npm install && npm run dev
```

First boot seeds a **Lab** customer with a local shell and Cisco/PAN/Forti simulators, so
you can work on the terminal without touching real gear.

## The one rule that matters

**`./data` is a credential vault.** It holds hosts, usernames, stored passwords and SSH host
keys. It is gitignored — keep it that way. Never paste its contents into an issue, a PR, or a
screenshot. When filing a bug, use the Lab simulators to reproduce.

## Layout

| Path | What |
|---|---|
| `backend/app/` | FastAPI service — `main.py`, `terminal_hub.py` (SSH/websocket), `crypto.py` + `hostkeys.py` (vault), `ai_service.py` + `llm/`, `mcp_server.py`, `simulators.py`, `toolkit/` |
| `frontend/src/` | React 19 + Vite. `App.tsx` is the shell, `components/` the panels, `themes.ts` the terminal palettes |
| `desktop/` | Electron shell |

## Style

Match the file you are editing. The codebase favours comments that explain *why* a
non-obvious choice was made, not *what* the line does — if a comment would only restate the
code, leave it out.

## Pull requests

1. Branch from `main`.
2. Keep it focused — one concern per PR.
3. `cd frontend && npm run build` must pass.
4. Say what you changed and how you tested it. "Tested against the Lab simulators" is a fine answer.

## Adding a terminal theme

Themes live in `frontend/src/themes.ts`. Add a `ChromeTheme` entry — the Settings → Appearance
tiles pick it up automatically and render a live preview from the values you supply. Check the
`red` and `green` you choose stay legible against your `background`; that preview exists
precisely so a theme cannot ship unreadable.
