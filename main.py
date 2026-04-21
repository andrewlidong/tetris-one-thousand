"""Top-level entry point used by pygbag to build the web bundle.

Also works as a plain `python main.py` for local runs. For day-to-day
native play, `python -m tetris` is the canonical command.
"""

from __future__ import annotations

import asyncio

from tetris.main import run


def _main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    _main()
