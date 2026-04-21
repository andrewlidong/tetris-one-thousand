# Tetris

Modern Tetris in Python with `pygame-ce`. Follows the Tetris Guideline: 7-bag,
SRS rotation with kicks, hold, 5-piece preview, ghost piece, lock delay,
soft/hard drop, T-spins, back-to-back, and combo scoring.

Structured to later build for the web with [`pygbag`](https://pypi.org/project/pygbag/)
(compiles pygame apps to WebAssembly).

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

## Build for web (future)

```sh
uv add --dev pygbag
uv run pygbag src/tetris/main.py
# → build/web/ — serve as static files
```
