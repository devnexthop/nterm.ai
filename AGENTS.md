# NTerm — canonical agent rules

**This file is canonical.** Claude Code, Cursor and Codex all read it natively.
`CLAUDE.md` is only a pointer — never write rules there.

**nterm.ai** — a network-engineer terminal for Cisco, Palo Alto and Fortinet. SecureCRT
session vault, PuTTY-grade SSH, Warp-style AI, built-in syslog / TFTP / DHCP, and an
engineer bench feed. Product of **ValeronLabs LLC**.

---

## ⚠️ THIS REPO IS PUBLIC

`devnexthop/nterm.ai` is public despite living in a private-looking org. Anything
committed here is readable by competitors and customers, immediately and permanently —
a later `git rm` does not remove it from history.

**Before adding any file, ask whether a competitor may read it.** `.gitignore` already
excludes the categories that must never ship:

| Excluded | Why |
|---|---|
| `site/` | the marketing site |
| `design/` | artboards, drafts, positioning notes |
| `docs/`, `docs/internal/` | internal documentation |
| `dev/` (`DEVPLAN.md`), `resource/` | roadmaps, strategy, competitive research |
| `relay/`, `scripts/deploy-site.sh`, `scripts/nginx-*.conf` | deploy + relay infrastructure |
| `relay-token*`, `*.token`, `.env` | secrets |
| `**/*competitive*`, `**/*strategy*`, `*.private.md` | catch-alls |

The public repo ships **only what is needed to build and run NTerm**.

This has already been violated once: `design/` was committed on 2026-08-26 while
recovering files from a scratch folder and removed the same day (`ef2fe14`). It is still
in history.

**Open gap:** the excluded paths live on this Mac and in **no git repo at all**, so they
do not reach the Windows box or survive a disk failure. `.gitignore` says they belong in
"a separate private repo" — that repo does not exist yet. Until it does, treat
`site/`, `relay/`, `design/` and `scripts/deploy-site.sh` as single-copy and back them up
manually.

---

## Run it

Docker is the supported local path. Needs Docker Desktop (Mac/Windows) or Docker Engine.

```bash
docker compose up --build          # http://localhost:8787
docker compose down                # stop
```

Lab toolkit (binds UDP 514 / 69 / 67 — skip until real gear points at the box):

```bash
docker compose -f docker-compose.yml -f docker-compose.lab.yml up --build
```

Without Docker: backend `uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload`
(venv + `requirements.txt`); frontend `npm install && npm run dev`; desktop shell
`cd desktop && npm start`.

First boot seeds a Lab customer with local shell plus Cisco/PAN/Forti simulators.

## `./data` is a credential vault

Session data — hosts, usernames, stored credentials, SSH host keys — lives in `./data`,
bind-mounted to `/data`. **Treat it like a password database.** It is gitignored; keep it
that way. `rm -rf data` wipes the vault and is not recoverable. Never paste its contents
into a chat, an issue, or a commit.

## Layout

| Path | What |
|---|---|
| `backend/app/` | FastAPI service — `main.py`, `terminal_hub.py` (SSH/websocket), `crypto.py` + `hostkeys.py` (vault), `ai_service.py` + `llm/`, `mcp_server.py` + `mcp_client.py`, `simulators.py`, `bench_feed.py`, `toolkit/` (syslog/TFTP/DHCP) |
| `frontend/` | web UI |
| `desktop/` | Electron shell (`main.cjs`, `preload.cjs`) |
| `relay/` | share-link relay — **not in the public repo** |
| `site/` | marketing site + `bench-feed.json` — **not in the public repo** |
| `data/` | the vault — never committed |

## Engineer bench feed

NTerm pulls cookbooks, runbooks and lookups from `https://nterm.ai/bench-feed.json`
(override with `NTERM_BENCH_URL`). Contract: `GET /api/architect/example-feed`. Mode
**merge** (default) overlays remote on built-in; if nterm.ai is unreachable NTerm keeps
the last cache, then falls back to built-in. Host `site/bench-feed.json` so that URL
returns JSON.

## Estate rules

Working tree is `~/gitsync/nterm.ai` — one tree per repo, never a checkout in a
cloud-synced folder. A duplicate clone at `~/nterm-design/repo` caused a split-brain scare
on 2026-08-26 and was removed.

Cross-project rules and session skills come from `~/gitsync/devwork-kit`:

```bash
git -C ~/gitsync/devwork-kit pull --ff-only && ~/gitsync/devwork-kit/sync-kit.sh
```

Claim a row in `netconverter-project-merger/docs/ai-coordination/NOW.md` before writing —
that lock covers every product, not just NetConverter.

Version lives in `VERSION` (currently `0.1.0`). Installers (Windows EXE / Mac DMG) come
later; local test is Docker.
