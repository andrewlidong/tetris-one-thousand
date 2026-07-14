from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class Action(StrEnum):
    """Actions a player can take on their piece."""

    MOVE_LEFT = "left"
    MOVE_RIGHT = "right"
    ROTATE_CW = "rotate_cw"
    ROTATE_CCW = "rotate_ccw"
    SOFT_DROP = "soft_drop"
    HARD_DROP = "hard_drop"
    HOLD = "hold"


class CellColor(IntEnum):
    """Each tetromino type maps to a color. 0 = empty."""

    EMPTY = 0
    I = 1
    O = 2
    T = 3
    S = 4
    Z = 5
    J = 6
    L = 7


class PieceType(StrEnum):
    I = "I"
    O = "O"
    T = "T"
    S = "S"
    Z = "Z"
    J = "J"
    L = "L"


# Maps PieceType to its CellColor for rendering
PIECE_COLORS: dict[PieceType, CellColor] = {
    PieceType.I: CellColor.I,
    PieceType.O: CellColor.O,
    PieceType.T: CellColor.T,
    PieceType.S: CellColor.S,
    PieceType.Z: CellColor.Z,
    PieceType.J: CellColor.J,
    PieceType.L: CellColor.L,
}


@dataclass(frozen=True)
class Position:
    """Row/column coordinate on the board. Row 0 is the top."""

    row: int
    col: int


@dataclass
class PieceState:
    """The current state of one player's falling piece."""

    piece_type: PieceType
    position: Position  # top-left anchor point
    rotation: int  # 0, 1, 2, 3 (SRS rotation states)

    def moved(self, d_row: int, d_col: int) -> PieceState:
        """Return a new PieceState shifted by the given offset."""
        return PieceState(
            piece_type=self.piece_type,
            position=Position(self.position.row + d_row, self.position.col + d_col),
            rotation=self.rotation,
        )

    def rotated(self, direction: int) -> PieceState:
        """Return a new PieceState rotated. direction: +1 = CW, -1 = CCW."""
        return PieceState(
            piece_type=self.piece_type,
            position=self.position,
            rotation=(self.rotation + direction) % 4,
        )
