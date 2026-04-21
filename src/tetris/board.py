"""Playfield grid: collision, locking, line clearing, T-spin corner check."""

from __future__ import annotations

from .constants import BUFFER_ROWS, COLS, TOTAL_ROWS
from .pieces import Tetromino


class Board:
    def __init__(self) -> None:
        # grid[row][col] = None or piece-kind letter ("I", "O", ...)
        self.grid: list[list[str | None]] = [[None] * COLS for _ in range(TOTAL_ROWS)]

    def cell(self, col: int, row: int) -> str | None:
        if row < 0 or row >= TOTAL_ROWS or col < 0 or col >= COLS:
            return "#"  # walls/floor are "occupied"
        return self.grid[row][col]

    def in_bounds(self, col: int, row: int) -> bool:
        return 0 <= col < COLS and 0 <= row < TOTAL_ROWS

    def collides(
        self,
        piece: Tetromino,
        rot: int | None = None,
        dx: int = 0,
        dy: int = 0,
    ) -> bool:
        """True if placing `piece` at (x+dx, y+dy) with `rot` would overlap a block or wall."""
        r = piece.rot if rot is None else rot
        for c, rr in piece.cells(rot=r, x=piece.x + dx, y=piece.y + dy):
            if c < 0 or c >= COLS or rr >= TOTAL_ROWS:
                return True
            if rr < 0:
                continue  # above the buffer is OK (pieces spawn partially there)
            if self.grid[rr][c] is not None:
                return True
        return False

    def lock(self, piece: Tetromino) -> None:
        for c, r in piece.cells():
            if 0 <= r < TOTAL_ROWS and 0 <= c < COLS:
                self.grid[r][c] = piece.kind

    def clear_lines(self) -> list[int]:
        """Remove full rows. Returns the list of cleared row indices (absolute, incl. buffer)."""
        cleared: list[int] = []
        new_grid: list[list[str | None]] = []
        for r in range(TOTAL_ROWS):
            if all(cell is not None for cell in self.grid[r]):
                cleared.append(r)
            else:
                new_grid.append(self.grid[r])
        # Pad empty rows at the top to restore height
        for _ in range(len(cleared)):
            new_grid.insert(0, [None] * COLS)
        self.grid = new_grid
        return cleared

    def piece_in_playfield(self, piece: Tetromino) -> bool:
        """True if any of the piece's cells is in the visible playfield."""
        return any(r >= BUFFER_ROWS for _c, r in piece.cells())

    def t_spin_corners(self, piece: Tetromino) -> tuple[int, int]:
        """Return (total_filled, front_filled) for the T-piece 4 corners.

        Corners are the 4 diagonals around the T's 3x3 bounding-box center (1, 1).
        The two "front" corners are the two adjacent to the T's tip per rotation.
        """
        if piece.kind != "T":
            return (0, 0)
        cx = piece.x + 1
        cy = piece.y + 1
        corners = [
            (cx - 1, cy - 1),  # TL
            (cx + 1, cy - 1),  # TR
            (cx - 1, cy + 1),  # BL
            (cx + 1, cy + 1),  # BR
        ]
        # Which corners are "front" (adjacent to the T's tip) per rotation state.
        # State 0: tip up → TL, TR are front.
        # State 1 (R): tip right → TR, BR are front.
        # State 2: tip down → BL, BR are front.
        # State 3 (L): tip left → TL, BL are front.
        front_idx = {0: (0, 1), 1: (1, 3), 2: (2, 3), 3: (0, 2)}[piece.rot]
        filled = [self.cell(c, r) is not None for (c, r) in corners]
        total = sum(filled)
        front = int(filled[front_idx[0]]) + int(filled[front_idx[1]])
        return (total, front)
