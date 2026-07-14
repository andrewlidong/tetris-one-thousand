from server.game.board import Board
from server.game.types import CellColor, PieceState, PieceType, Position


def test_board_dimensions():
    board = Board(width=30, height=40)
    assert board.width == 30
    assert board.height == 40
    assert len(board.grid) == 40
    assert len(board.grid[0]) == 30


def test_board_starts_empty():
    board = Board()
    for row in board.grid:
        assert all(cell == CellColor.EMPTY for cell in row)


def test_expand_width():
    board = Board(width=10, height=20)
    board.expand_width(20)
    assert board.width == 20
    assert all(len(row) == 20 for row in board.grid)


def test_expand_width_preserves_cells():
    board = Board(width=10, height=20)
    board.grid[19][5] = CellColor.T
    board.expand_width(20)
    assert board.grid[19][5] == CellColor.T
    assert board.grid[19][15] == CellColor.EMPTY


def test_expand_width_no_shrink():
    board = Board(width=20, height=20)
    board.expand_width(10)
    assert board.width == 20


def test_is_valid_position():
    board = Board(width=10, height=20)
    # Piece at top-left corner should be valid
    piece = PieceState(PieceType.O, Position(0, 0), 0)
    assert board.is_valid_position(piece)


def test_is_valid_position_out_of_bounds():
    board = Board(width=10, height=20)
    # Piece hanging off left edge
    piece = PieceState(PieceType.I, Position(0, -1), 0)
    assert not board.is_valid_position(piece)


def test_is_valid_position_collision():
    board = Board(width=10, height=20)
    # Place a cell on the board
    board.grid[1][0] = CellColor.T
    # O piece at (0,0) occupies (0,0), (0,1), (1,0), (1,1) — collides at (1,0)
    piece = PieceState(PieceType.O, Position(0, 0), 0)
    assert not board.is_valid_position(piece)


def test_lock_piece():
    board = Board(width=10, height=20)
    piece = PieceState(PieceType.O, Position(18, 0), 0)
    board.lock_piece(piece)
    assert board.grid[18][0] == CellColor.O
    assert board.grid[18][1] == CellColor.O
    assert board.grid[19][0] == CellColor.O
    assert board.grid[19][1] == CellColor.O


def test_clear_lines_none():
    board = Board(width=10, height=20)
    assert board.clear_lines() == []


def test_clear_lines_one():
    board = Board(width=10, height=20)
    # Fill the bottom row
    for col in range(10):
        board.grid[19][col] = CellColor.I
    cleared = board.clear_lines()
    assert cleared == [19]
    # Bottom row should now be empty (shifted down)
    assert all(cell == CellColor.EMPTY for cell in board.grid[19])


def test_clear_lines_preserves_above():
    board = Board(width=10, height=20)
    # Put something on row 18
    board.grid[18][3] = CellColor.T
    # Fill row 19 completely
    for col in range(10):
        board.grid[19][col] = CellColor.I
    cleared = board.clear_lines()
    assert cleared == [19]
    # Row 18's content should have shifted down to row 19
    assert board.grid[19][3] == CellColor.T


def test_is_topped_out():
    board = Board(width=10, height=20)
    assert not board.is_topped_out()
    board.grid[0][5] = CellColor.I
    assert board.is_topped_out()
