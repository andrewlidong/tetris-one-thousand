# Tetris

Modern Tetris in Python with `pygame-ce`. Follows the Tetris Guideline: 7-bag,
SRS rotation with kicks, hold, 5-piece preview, ghost piece, lock delay,
soft/hard drop, T-spins, back-to-back, and combo scoring.

Also builds for the web with [`pygbag`](https://pypi.org/project/pygbag/)
(compiles pygame apps to WebAssembly). Auto-deployed to GitHub Pages on push
to `main`.

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

On every push to `main`, `.github/workflows/deploy-pages.yml` builds the web
bundle and publishes it to GitHub Pages. Enable Pages once in **repo →
Settings → Pages → Source: GitHub Actions**.
