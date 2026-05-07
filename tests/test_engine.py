from server.game.engine import Bag, GameEngine
from server.game.types import Action, PieceType


def test_bag_returns_all_types():
    """A bag should return all 7 piece types before repeating."""
    bag = Bag()
    pieces = [bag.next() for _ in range(7)]
    assert set(pieces) == set(PieceType)


def test_bag_repeats():
    bag = Bag()
    first_seven = [bag.next() for _ in range(7)]
    second_seven = [bag.next() for _ in range(7)]
    assert set(first_seven) == set(PieceType)
    assert set(second_seven) == set(PieceType)


def test_add_player():
    engine = GameEngine(width=20)
    piece = engine.add_player("player1")
    assert piece is not None
    assert "player1" in engine.active_pieces


def test_add_player_expands_board():
    engine = GameEngine(width=20)
    # Add enough players that board needs to expand
    for i in range(15):
        engine.add_player(f"player{i}")
    assert engine.board.width >= 30  # 15 * 2 = 30


def test_remove_player():
    engine = GameEngine()
    engine.add_player("player1")
    engine.remove_player("player1")
    assert "player1" not in engine.active_pieces
    assert "player1" not in engine.bags


def test_move_left():
    engine = GameEngine(width=20)
    engine.add_player("p1")
    piece_before = engine.active_pieces["p1"]
    col_before = piece_before.position.col

    if col_before > 0:
        result = engine.process_action("p1", Action.MOVE_LEFT)
        assert result is True
        assert engine.active_pieces["p1"].position.col == col_before - 1


def test_move_right():
    engine = GameEngine(width=20)
    engine.add_player("p1")
    piece_before = engine.active_pieces["p1"]
    col_before = piece_before.position.col

    if col_before < engine.board.width - 4:
        result = engine.process_action("p1", Action.MOVE_RIGHT)
        assert result is True
        assert engine.active_pieces["p1"].position.col == col_before + 1


def test_soft_drop():
    engine = GameEngine(width=20)
    engine.add_player("p1")
    row_before = engine.active_pieces["p1"].position.row
    engine.process_action("p1", Action.SOFT_DROP)
    assert engine.active_pieces["p1"].position.row == row_before + 1


def test_hard_drop_locks_piece():
    engine = GameEngine(width=20)
    engine.add_player("p1")
    old_piece_type = engine.active_pieces["p1"].piece_type
    engine.process_action("p1", Action.HARD_DROP)
    # After hard drop, the player should have a new piece (different position at top)
    new_piece = engine.active_pieces.get("p1")
    assert new_piece is not None
    assert new_piece.position.row == 0  # spawned at top


def test_tick_moves_pieces_down():
    engine = GameEngine(width=20)
    engine.add_player("p1")
    row_before = engine.active_pieces["p1"].position.row
    engine.tick()
    assert engine.active_pieces["p1"].position.row == row_before + 1


def test_tick_locks_piece_at_bottom():
    engine = GameEngine(width=20, height=10)
    engine.add_player("p1")
    # Move piece near the bottom
    for _ in range(20):
        engine.tick()
    # After enough ticks, piece should have locked and a new one spawned
    piece = engine.active_pieces.get("p1")
    # Either the player has a new piece at the top, or the game is over
    assert piece is None or piece.position.row < 5 or engine.game_over


def test_multiple_players():
    engine = GameEngine(width=100)
    for i in range(10):
        engine.add_player(f"p{i}")
    assert len(engine.active_pieces) == 10


def test_get_state():
    engine = GameEngine(width=20)
    engine.add_player("p1")
    state = engine.get_state()
    assert "grid" in state
    assert "active_pieces" in state
    assert "score" in state
    assert "lines_cleared" in state
    assert "board_width" in state
    assert "player_count" in state
    assert state["player_count"] == 1


def test_rotate():
    engine = GameEngine(width=20)
    engine.add_player("p1")
    piece_before = engine.active_pieces["p1"]
    rot_before = piece_before.rotation
    # T, S, Z, J, L, I all have distinct rotations
    if piece_before.piece_type != PieceType.O:
        result = engine.process_action("p1", Action.ROTATE_CW)
        assert result is True
        assert engine.active_pieces["p1"].rotation == (rot_before + 1) % 4


def test_active_pieces_collide():
    """Pieces from different players block each other instead of phasing through."""
    from server.game.types import PieceState, PieceType, Position
    engine = GameEngine(width=20)
    engine.add_player("p1")
    engine.add_player("p2")

    # Force-place p1's O-piece at row 5, col 5
    engine._release_cells("p1")
    engine.active_pieces["p1"] = PieceState(PieceType.O, Position(5, 5), 0)
    engine._claim_cells("p1", engine.active_pieces["p1"])

    # Try to place p2's O-piece on top of p1's piece — must fail
    overlapping = PieceState(PieceType.O, Position(5, 5), 0)
    assert engine._can_place("p2", overlapping) is False

    # Adjacent column must succeed
    next_to = PieceState(PieceType.O, Position(5, 7), 0)
    assert engine._can_place("p2", next_to) is True


def test_hard_drop_rests_on_other_player():
    """A hard-dropped piece resting on another active piece stays active —
    it doesn't lock in mid-air. It will fall along with the supporter."""
    from server.game.types import Action, PieceState, PieceType, Position
    engine = GameEngine(width=20)
    engine.add_player("p1")
    engine.add_player("p2")

    # Park p1's O-piece in mid-air at columns 5-6, row 20
    engine._release_cells("p1")
    p1_piece = PieceState(PieceType.O, Position(20, 5), 0)
    engine.active_pieces["p1"] = p1_piece
    engine._claim_cells("p1", p1_piece)

    # Drop p2's O-piece directly above p1's
    engine._release_cells("p2")
    p2_piece = PieceState(PieceType.O, Position(0, 5), 0)
    engine.active_pieces["p2"] = p2_piece
    engine._claim_cells("p2", p2_piece)

    engine.process_action("p2", Action.HARD_DROP)

    # p2 should rest at rows 18-19 (just above p1 at 20-21), still active
    assert "p2" in engine.active_pieces
    assert engine.active_pieces["p2"].position == Position(18, 5)
    # No cells got locked into the grid mid-air
    assert engine.board.grid[18][5] == 0
    assert engine.board.grid[20][5] == 0


def test_horizontal_move_carries_stacked_pieces():
    """Sliding the bottom piece left/right also drags the piece resting on it."""
    from server.game.types import Action, PieceState, PieceType, Position
    engine = GameEngine(width=20)
    engine.add_player("p1")
    engine.add_player("p2")

    # p1 at row 20-21, p2 stacked directly above at 18-19, both cols 5-6
    engine._release_cells("p1")
    engine.active_pieces["p1"] = PieceState(PieceType.O, Position(20, 5), 0)
    engine._claim_cells("p1", engine.active_pieces["p1"])

    engine._release_cells("p2")
    engine.active_pieces["p2"] = PieceState(PieceType.O, Position(18, 5), 0)
    engine._claim_cells("p2", engine.active_pieces["p2"])

    # p1 moves right — p2 should come along
    engine.process_action("p1", Action.MOVE_RIGHT)
    assert engine.active_pieces["p1"].position == Position(20, 6)
    assert engine.active_pieces["p2"].position == Position(18, 6)


def test_horizontal_move_blocked_by_stacked_collision():
    """If carrying the stack would collide with something, the whole move fails."""
    from server.game.types import Action, PieceState, PieceType, Position
    engine = GameEngine(width=20)
    engine.add_player("p1")
    engine.add_player("p2")

    # p1 at row 20, cols 5-6; p2 stacked above at 18-19, cols 5-6
    engine._release_cells("p1")
    engine.active_pieces["p1"] = PieceState(PieceType.O, Position(20, 5), 0)
    engine._claim_cells("p1", engine.active_pieces["p1"])
    engine._release_cells("p2")
    engine.active_pieces["p2"] = PieceState(PieceType.O, Position(18, 5), 0)
    engine._claim_cells("p2", engine.active_pieces["p2"])

    # Block p2's right neighbor with a locked grid cell
    engine.board.grid[18][7] = 1  # type: ignore[assignment]

    # p1 tries to move right. p2's new col would be 7, which is now a locked cell.
    # The whole move should fail; both stay put.
    result = engine.process_action("p1", Action.MOVE_RIGHT)
    assert result is False
    assert engine.active_pieces["p1"].position == Position(20, 5)
    assert engine.active_pieces["p2"].position == Position(18, 5)


def test_stacked_pieces_fall_together():
    """When p1's piece falls, p2's piece resting on top of it falls too."""
    from server.game.types import PieceState, PieceType, Position
    engine = GameEngine(width=20)
    engine.add_player("p1")
    engine.add_player("p2")

    # p1's piece at row 20-21 in mid-air; p2's piece resting on top at 18-19
    engine._release_cells("p1")
    engine.active_pieces["p1"] = PieceState(PieceType.O, Position(20, 5), 0)
    engine._claim_cells("p1", engine.active_pieces["p1"])

    engine._release_cells("p2")
    engine.active_pieces["p2"] = PieceState(PieceType.O, Position(18, 5), 0)
    engine._claim_cells("p2", engine.active_pieces["p2"])

    engine.tick()

    # Both pieces should have moved down by 1
    assert engine.active_pieces["p1"].position == Position(21, 5)
    assert engine.active_pieces["p2"].position == Position(19, 5)


def test_spawn_returns_none_when_blocked():
    """When the spawn area is full, spawn_piece returns None instead of
    setting a global game_over (so one player's top-out doesn't freeze a
    1000-player session)."""
    engine = GameEngine(width=20, height=6)
    engine.add_player("p1")
    # Fill the entire board so any spawn position collides
    for row in range(engine.board.height):
        for col in range(engine.board.width):
            engine.board.grid[row][col] = 1  # type: ignore[assignment]
    engine.active_pieces.pop("p1")
    result = engine.spawn_piece("p1")
    assert result is None
    assert not engine.game_over  # cooperative server: never globally over
