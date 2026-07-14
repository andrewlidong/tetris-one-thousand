"""Tetromino piece definitions using the Super Rotation System (SRS).

Each piece has 4 rotation states. Each state is a list of (row, col) offsets
relative to the piece's anchor position. These offsets define which cells the
piece occupies on the board.
"""

from .types import PieceState, PieceType, Position

# Rotation states for each piece type.
# Each entry is a tuple of 4 rotations, each rotation is a tuple of 4 (row, col) offsets.
SHAPES: dict[PieceType, tuple[tuple[tuple[int, int], ...], ...]] = {
    PieceType.I: (
        ((0, 0), (0, 1), (0, 2), (0, 3)),  # flat horizontal
        ((0, 2), (1, 2), (2, 2), (3, 2)),  # vertical
        ((2, 0), (2, 1), (2, 2), (2, 3)),  # flat (shifted down)
        ((0, 1), (1, 1), (2, 1), (3, 1)),  # vertical (shifted left)
    ),
    PieceType.O: (
        ((0, 0), (0, 1), (1, 0), (1, 1)),
        ((0, 0), (0, 1), (1, 0), (1, 1)),
        ((0, 0), (0, 1), (1, 0), (1, 1)),
        ((0, 0), (0, 1), (1, 0), (1, 1)),
    ),
    PieceType.T: (
        ((0, 1), (1, 0), (1, 1), (1, 2)),
        ((0, 1), (1, 1), (1, 2), (2, 1)),
        ((1, 0), (1, 1), (1, 2), (2, 1)),
        ((0, 1), (1, 0), (1, 1), (2, 1)),
    ),
    PieceType.S: (
        ((0, 1), (0, 2), (1, 0), (1, 1)),
        ((0, 1), (1, 1), (1, 2), (2, 2)),
        ((1, 1), (1, 2), (2, 0), (2, 1)),
        ((0, 0), (1, 0), (1, 1), (2, 1)),
    ),
    PieceType.Z: (
        ((0, 0), (0, 1), (1, 1), (1, 2)),
        ((0, 2), (1, 1), (1, 2), (2, 1)),
        ((1, 0), (1, 1), (2, 1), (2, 2)),
        ((0, 1), (1, 0), (1, 1), (2, 0)),
    ),
    PieceType.J: (
        ((0, 0), (1, 0), (1, 1), (1, 2)),
        ((0, 1), (0, 2), (1, 1), (2, 1)),
        ((1, 0), (1, 1), (1, 2), (2, 2)),
        ((0, 1), (1, 1), (2, 0), (2, 1)),
    ),
    PieceType.L: (
        ((0, 2), (1, 0), (1, 1), (1, 2)),
        ((0, 1), (1, 1), (2, 1), (2, 2)),
        ((1, 0), (1, 1), (1, 2), (2, 0)),
        ((0, 0), (0, 1), (1, 1), (2, 1)),
    ),
}

# SRS wall kick data: offsets to try when a rotation fails.
# Key is (from_rotation, to_rotation). Each value is a list of (row, col) offsets to try.
# Positive row = down, positive col = right.
WALL_KICKS: dict[tuple[int, int], tuple[tuple[int, int], ...]] = {
    (0, 1): ((0, -1), (-1, -1), (2, 0), (2, -1)),
    (1, 0): ((0, 1), (1, 1), (-2, 0), (-2, 1)),
    (1, 2): ((0, 1), (1, 1), (-2, 0), (-2, 1)),
    (2, 1): ((0, -1), (-1, -1), (2, 0), (2, -1)),
    (2, 3): ((0, 1), (-1, 1), (2, 0), (2, 1)),
    (3, 2): ((0, -1), (1, -1), (-2, 0), (-2, -1)),
    (3, 0): ((0, -1), (1, -1), (-2, 0), (-2, -1)),
    (0, 3): ((0, 1), (-1, 1), (2, 0), (2, 1)),
}

WALL_KICKS_I: dict[tuple[int, int], tuple[tuple[int, int], ...]] = {
    (0, 1): ((0, -2), (0, 1), (1, -2), (-2, 1)),
    (1, 0): ((0, 2), (0, -1), (-1, 2), (2, -1)),
    (1, 2): ((0, -1), (0, 2), (-2, -1), (1, 2)),
    (2, 1): ((0, 1), (0, -2), (2, 1), (-1, -2)),
    (2, 3): ((0, 2), (0, -1), (-1, 2), (2, -1)),
    (3, 2): ((0, -2), (0, 1), (1, -2), (-2, 1)),
    (3, 0): ((0, 1), (0, -2), (2, 1), (-1, -2)),
    (0, 3): ((0, -1), (0, 2), (-2, -1), (1, 2)),
}


def get_cells(piece: PieceState) -> list[Position]:
    """Get the absolute board positions occupied by this piece."""
    offsets = SHAPES[piece.piece_type][piece.rotation]
    return [Position(piece.position.row + dr, piece.position.col + dc) for dr, dc in offsets]


def get_wall_kicks(
    piece_type: PieceType, from_rot: int, to_rot: int
) -> tuple[tuple[int, int], ...]:
    """Get the wall kick offsets to try for a rotation."""
    key = (from_rot, to_rot)
    if piece_type == PieceType.I:
        return WALL_KICKS_I.get(key, ())
    if piece_type == PieceType.O:
        return ()  # O piece doesn't need wall kicks
    return WALL_KICKS.get(key, ())
