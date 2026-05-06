from server.game.piece import get_cells, SHAPES
from server.game.types import PieceState, PieceType, Position


def test_get_cells_returns_four_cells():
    """Every tetromino has exactly 4 cells."""
    for piece_type in PieceType:
        for rotation in range(4):
            piece = PieceState(piece_type, Position(0, 0), rotation)
            cells = get_cells(piece)
            assert len(cells) == 4, f"{piece_type.value} rotation {rotation} has {len(cells)} cells"


def test_get_cells_offset_by_position():
    """Cells should be offset by the piece's position."""
    piece = PieceState(PieceType.O, Position(5, 10), 0)
    cells = get_cells(piece)
    rows = {c.row for c in cells}
    cols = {c.col for c in cells}
    assert min(rows) >= 5
    assert min(cols) >= 10


def test_all_rotations_defined():
    """Every piece type should have exactly 4 rotation states."""
    for piece_type in PieceType:
        assert len(SHAPES[piece_type]) == 4


def test_piece_state_moved():
    piece = PieceState(PieceType.T, Position(3, 5), 0)
    moved = piece.moved(1, -1)
    assert moved.position == Position(4, 4)
    assert moved.piece_type == PieceType.T
    assert moved.rotation == 0


def test_piece_state_rotated():
    piece = PieceState(PieceType.T, Position(3, 5), 0)
    assert piece.rotated(1).rotation == 1
    assert piece.rotated(-1).rotation == 3
    # Wrap around
    piece2 = PieceState(PieceType.T, Position(0, 0), 3)
    assert piece2.rotated(1).rotation == 0


def test_i_piece_horizontal():
    """I piece in rotation 0 should be 4 cells in a horizontal line."""
    piece = PieceState(PieceType.I, Position(0, 0), 0)
    cells = get_cells(piece)
    rows = [c.row for c in cells]
    cols = sorted(c.col for c in cells)
    assert all(r == 0 for r in rows), "I piece rotation 0 should be on one row"
    assert cols == [0, 1, 2, 3]
