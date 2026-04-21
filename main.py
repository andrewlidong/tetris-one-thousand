"""Top-level entry point used by pygbag to build the web bundle.

pygbag requires `asyncio.run(...)` at module top level (not inside a
function or __main__ guard) so its Pyodide runtime can schedule the
coroutine on the existing event loop. Keep this file minimal.
"""

import asyncio

from tetris.main import run

asyncio.run(run())
