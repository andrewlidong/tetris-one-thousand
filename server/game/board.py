"""The game board — a dynamically-sized grid of cells.

The board can grow wider as more players join. Height is fixed.
Row 0 is the top of the board.
"""

from .piece import get_cells
from .types import PIECE_COLORS, CellColor, PieceState, Position


class Board:
    def __init__(self, width: int = 20, height: int = 40):
        self.width = width
        self.height = height
        # grid[row][col] — row 0 is top
        self.grid: list[list[CellColor]] = [[CellColor.EMPTY] * width for _ in range(height)]

    def expand_width(self, new_width: int) -> None:
        """Expand the board by adding empty columns on the right."""
        if new_width <= self.width:
            return
        extra = new_width - self.width
        for row in self.grid:
            row.extend([CellColor.EMPTY] * extra)
        self.width = new_width

    def in_bounds(self, pos: Position) -> bool:
        return 0 <= pos.row < self.height and 0 <= pos.col < self.width

    def is_empty(self, pos: Position) -> bool:
        return self.in_bounds(pos) and self.grid[pos.row][pos.col] == CellColor.EMPTY

    def is_valid_position(self, piece: PieceState) -> bool:
        """Check if a piece can occupy its current position (no collisions, in bounds)."""
        for cell in get_cells(piece):
            if not self.in_bounds(cell):
                return False
            if self.grid[cell.row][cell.col] != CellColor.EMPTY:
                return False
        return True

    def lock_piece(self, piece: PieceState) -> None:
        """Lock a piece into the grid (it becomes part of the board)."""
        color = PIECE_COLORS[piece.piece_type]
        for cell in get_cells(piece):
            if self.in_bounds(cell):
                self.grid[cell.row][cell.col] = color

    def clear_lines(self) -> list[int]:
        """Remove fully filled rows and shift everything above down.

        Returns the row indices that were cleared (positions before the shift),
        so clients can animate a flash where each line was completed.
        """
        cleared_rows: list[int] = []
        # Walk from bottom to top
        write_row = self.height - 1
        for read_row in range(self.height - 1, -1, -1):
            if all(cell != CellColor.EMPTY for cell in self.grid[read_row]):
                cleared_rows.append(read_row)
            else:
                if write_row != read_row:
                    self.grid[write_row] = self.grid[read_row]
                write_row -= 1

        # Fill the top rows that were cleared with empty rows
        for row in range(write_row + 1):
            self.grid[row] = [CellColor.EMPTY] * self.width

        return cleared_rows

    def is_topped_out(self) -> bool:
        """Check if any cell in the top 4 rows has a locked piece (game over condition)."""
        for row in range(4):
            for col in range(self.width):
                if self.grid[row][col] != CellColor.EMPTY:
                    return True
        return False

    def get_grid_snapshot(self) -> list[list[int]]:
        """Return the grid as a 2D list of ints (for serialization)."""
        return [[int(cell) for cell in row] for row in self.grid]
