# Tetris

Two games in one repo:

1. **Multiplayer Tetris** (`server/` + `static/`) — one giant shared board for
   up to 1000 players, over WebSockets. See [Multiplayer](#multiplayer).
2. **Single-player Tetris** (`tetris/`) — modern guideline Tetris with
   `pygame-ce`, also compiled to WebAssembly for the browser.

## Multiplayer

Everyone plays on the *same* board, which grows wider as players join (20 →
500 columns, 2 per player). Each player has their own falling piece; line
clears credit the player who locked the completing piece. When the board tops
out it wipes and a new round starts — scores and players carry over, so the
game never ends.

**Gameplay** — 7-bag randomizer, SRS rotation with wall kicks (including the
I-piece's own kick table), ghost piece, hold queue, next preview, lock delay
(one gravity tick of grace to slide/rotate a grounded piece), gravity that
ramps as the team clears lines (0.5s → 0.15s per row, resetting each round),
and a periodic 30-second **frenzy** of double points. Triples and Tetrises
are announced to the whole board with the scorer's name.

**Multiplayer** — per-player scores and a live top-10 leaderboard, name tags
above other players' pieces, reconnect identity (a localStorage token restores
your name and score across refreshes and drops), persistent all-time high
scores shown on the title screen (`GET /highscores`, file path via
`HIGHSCORE_FILE`), idle cleanup (2 minutes without input removes your piece
until you press a key), and per-connection rate limiting.

**Client** — canvas renderer with beveled cells, line-clear flashes,
hard-drop particles, WebAudio sound effects (mute with M), a clickable
minimap of the whole board, viewport auto-scroll that follows your piece,
DAS key repeat, and touch controls + responsive layout for phones.

**Scale** — server-authoritative engine on a single asyncio process; delta
broadcasts (only changed cells go over the wire); fan-out serialized once and
sent concurrently in chunks of 50 so one slow client can't stall the rest;
failed actions don't broadcast at all.

```sh
uv sync
uv run uvicorn server.main:app --port 8000
# open http://localhost:8000 — one tab per player
```

Controls: arrows move & soft-drop, `Z`/`X` rotate, `Space` hard-drop,
`C`/`Shift` hold, `M` mute. On touch devices an on-screen button bar appears,
and tapping the board rotates.

Tests and load test:

```sh
uv run pytest tests/
uv run python -m tests.load_test --players 100 --duration 30 --url ws://localhost:8000/ws
```

Deploys via the Render blueprint in `render.yaml` (free tier: sleeps after
15 minutes idle, and the high-score file resets on redeploy). Tuning knobs —
tick rate, gravity ramp, frenzy timing, rate limits, board size — are all
constants in `server/config.py`.

## Single-player

Modern Tetris in Python with `pygame-ce`. Follows the Tetris Guideline: 7-bag,
SRS rotation with kicks, hold, 5-piece preview, ghost piece, lock delay,
soft/hard drop, T-spins, back-to-back, and combo scoring.

Also builds for the web with [`pygbag`](https://pypi.org/project/pygbag/)
(compiles pygame apps to WebAssembly). Auto-deployed to Cloudflare Pages on
push to `main`.

## Requirements

- [`uv`](https://docs.astral.sh/uv/) (Astral's Python package manager).
  `uv` will install the required Python version automatically.

## Run

```sh
uv sync
uv run python -m tetris
```

## Controls

| Action          | Keys                |
| --------------- | ------------------- |
| Move left/right | ← / →               |
| Soft drop       | ↓                   |
| Hard drop       | Space               |
| Rotate CW       | ↑ / X               |
| Rotate CCW      | Z / Ctrl            |
| Hold            | C / Shift           |
| Pause           | P / Esc             |
| Restart         | R                   |
| Quit            | Esc (on Game Over)  |

## Dev

```sh
uv run ruff check .
uv run ruff format .
```

## Build for web

```sh
uv run pygbag --build --app_name tetris --title "Tetris" main.py
# → build/web/  — static HTML/WASM bundle, serve anywhere.
```

To preview locally:

```sh
uv run python -m http.server --directory build/web 8000
# open http://localhost:8000
```

## Deploy

On every push to `main`, `.github/workflows/deploy-cloudflare.yml` builds the
web bundle and publishes it to Cloudflare Pages (project
`tetris-one-thousand`). URL: `https://tetris-one-thousand.pages.dev`.

### One-time setup

1. **Create a Cloudflare API token** at
   <https://dash.cloudflare.com/profile/api-tokens>. Use the **"Edit Cloudflare
   Workers"** template, or a custom token with these permissions:
   - Account → **Cloudflare Pages** → **Edit**
   - User → **User Details** → **Read** (optional, avoids a warning)
2. **Find your Cloudflare account ID** on the right-hand sidebar of any zone
   in the Cloudflare dashboard (or under Workers & Pages).
3. **Add both as GitHub Actions secrets** at
   <https://github.com/andrewlidong/tetris-one-thousand/settings/secrets/actions>:
   - `CLOUDFLARE_API_TOKEN`
   - `CLOUDFLARE_ACCOUNT_ID`

After that, pushing to `main` triggers a build + deploy. The Pages project
auto-creates on the first successful run.
