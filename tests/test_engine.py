from server.game.engine import Bag, GameEngine
from server.game.types import Action, PieceState, PieceType, Position


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
    # After enough ticks, the piece should have locked and a new one spawned
    piece = engine.active_pieces.get("p1")
    assert piece is not None


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


def test_jammed_spawn_starts_new_round():
    """When no spawn column is free, the board wipes and a new round begins."""
    engine = GameEngine(width=10, height=6)
    engine.add_player("p1")
    # Fill the whole board so nothing can spawn
    # (add_player may have expanded the board to BOARD_MIN_WIDTH)
    for row in range(engine.board.height):
        for col in range(engine.board.width):
            engine.board.grid[row][col] = 1  # type: ignore[assignment]
    engine.active_pieces.pop("p1")

    result = engine.spawn_piece("p1")

    assert result is not None  # spawned on the freshly wiped board
    assert engine.round == 2
    # Board is empty again (except nothing has locked yet)
    assert all(cell == 0 for row in engine.board.grid for cell in row)


def test_topout_starts_new_round_and_keeps_players():
    engine = GameEngine(width=10, height=6)
    engine.add_player("p1")
    engine.scores["p1"] = 500
    # Fill the top rows (below the spawn area is irrelevant — top 4 rows trigger it)
    for row in range(4):
        for col in range(10):
            engine.board.grid[row][col] = 1  # type: ignore[assignment]

    engine._lock_piece("p1")

    assert engine.round == 2
    assert "p1" in engine.active_pieces  # respawned, not eliminated
    assert engine.scores["p1"] == 500  # score survives the reset


def test_round_reset_flag_in_delta():
    engine = GameEngine(width=10, height=6)
    engine.add_player("p1")
    engine._reset_round()
    delta = engine.get_delta()
    assert delta["round_reset"] is True
    assert delta["round"] == 2
    # Flag is consumed — next delta doesn't repeat it
    assert "round_reset" not in engine.get_delta()


def test_hold_swaps_piece():
    engine = GameEngine(width=20)
    engine.add_player("p1")
    original_type = engine.active_pieces["p1"].piece_type

    result = engine.process_action("p1", Action.HOLD)

    assert result is True
    assert engine.held_pieces["p1"] == original_type
    assert "p1" in engine.active_pieces  # a replacement piece spawned


def test_hold_only_once_per_piece():
    engine = GameEngine(width=20)
    engine.add_player("p1")
    assert engine.process_action("p1", Action.HOLD) is True
    # Second hold before locking is rejected
    assert engine.process_action("p1", Action.HOLD) is False
    # After the piece locks, holding is allowed again
    engine.process_action("p1", Action.HARD_DROP)
    assert engine.process_action("p1", Action.HOLD) is True


def test_hold_returns_previously_held_piece():
    engine = GameEngine(width=20)
    engine.add_player("p1")
    first_type = engine.active_pieces["p1"].piece_type
    engine.process_action("p1", Action.HOLD)
    engine.process_action("p1", Action.HARD_DROP)  # lock, re-enabling hold
    engine.process_action("p1", Action.HOLD)
    # The piece we get back is the one we stashed first
    assert engine.active_pieces["p1"].piece_type == first_type


def test_line_clear_credits_locking_player():
    engine = GameEngine(width=20, height=10)
    engine.add_player("p1")
    # Fill the bottom row except columns 0-3, then drop a flat I piece there
    for col in range(4, 20):
        engine.board.grid[9][col] = 1  # type: ignore[assignment]
    engine.active_pieces["p1"] = PieceState(
        piece_type=PieceType.I, position=Position(0, 0), rotation=0
    )

    engine.process_action("p1", Action.HARD_DROP)

    assert engine.lines_cleared == 1
    assert engine.scores["p1"] == 100  # personal credit
    assert engine.score == 100  # team score too


def test_set_name_trims_and_caps():
    engine = GameEngine(width=20)
    engine.add_player("p1", name="  Andrew  ")
    assert engine.names["p1"] == "Andrew"
    engine.set_name("p1", "x" * 50)
    assert len(engine.names["p1"]) == 16
    # Blank names are ignored, keeping the old one
    engine.set_name("p1", "   ")
    assert len(engine.names["p1"]) == 16


def test_lock_delay_gives_grace_tick():
    """A grounded piece survives one tick and locks on the second."""
    engine = GameEngine(width=20, height=6)
    engine.add_player("p1")
    # Place an O piece resting on the floor (occupies rows 4 and 5)
    engine.active_pieces["p1"] = PieceState(
        piece_type=PieceType.O, position=Position(4, 0), rotation=0
    )

    engine.tick()  # grounded tick 1: grace, not locked
    assert all(cell == 0 for row in engine.board.grid for cell in row)
    assert engine.active_pieces["p1"].position.row == 4

    engine.tick()  # grounded tick 2: locks
    assert engine.board.grid[5][0] != 0


def test_lock_delay_resets_when_piece_falls_again():
    """Sliding off a ledge onto open air restarts the lock-delay grace."""
    engine = GameEngine(width=20, height=6)
    engine.add_player("p1")
    engine.active_pieces["p1"] = PieceState(
        piece_type=PieceType.O, position=Position(4, 0), rotation=0
    )
    engine.tick()  # grounded once
    assert engine._grounded_ticks.get("p1") == 1
    # Simulate the piece being able to fall again (e.g. support vanished)
    engine.active_pieces["p1"] = PieceState(
        piece_type=PieceType.O, position=Position(0, 0), rotation=0
    )
    engine.tick()  # falls -> grace counter cleared
    assert "p1" not in engine._grounded_ticks


def test_idle_player_piece_removed_and_respawned_on_input():
    from server.config import IDLE_TICKS_BEFORE_REMOVE

    engine = GameEngine(width=20)
    engine.add_player("p1")

    for _ in range(IDLE_TICKS_BEFORE_REMOVE):
        engine.tick()

    assert "p1" not in engine.active_pieces  # removed for idleness
    assert "p1" in engine.bags  # but not kicked from the game

    # Any input brings them back with a fresh piece
    assert engine.process_action("p1", Action.SOFT_DROP) is True
    assert "p1" in engine.active_pieces
    assert engine.idle_ticks["p1"] == 0


def test_actions_reset_idle_counter():
    engine = GameEngine(width=20)
    engine.add_player("p1")
    for _ in range(50):
        engine.tick()
    assert engine.idle_ticks["p1"] == 50
    engine.process_action("p1", Action.SOFT_DROP)
    assert engine.idle_ticks["p1"] == 0


def test_cleared_rows_reported_in_delta():
    engine = GameEngine(width=20, height=10)
    engine.add_player("p1")
    engine.get_delta()  # drain join-time dirt
    for col in range(4, 20):
        engine.board.grid[9][col] = 1  # type: ignore[assignment]
    engine.active_pieces["p1"] = PieceState(
        piece_type=PieceType.I, position=Position(0, 0), rotation=0
    )

    engine.process_action("p1", Action.HARD_DROP)

    delta = engine.get_delta()
    assert delta["cleared_rows"] == [9]
    # Consumed: not repeated in the next delta
    assert "cleared_rows" not in engine.get_delta()


def test_gravity_ramps_with_lines_and_resets_each_round():
    from server.config import LINES_PER_SPEEDUP, MIN_TICK_RATE, SPEEDUP_PER_LEVEL, TICK_RATE

    engine = GameEngine(width=20)
    assert engine.speed_level == 0
    assert engine.tick_interval == TICK_RATE

    engine.lines_this_round = LINES_PER_SPEEDUP * 3
    assert engine.speed_level == 3
    assert engine.tick_interval == TICK_RATE - 3 * SPEEDUP_PER_LEVEL

    # Clamped at the floor no matter how many lines
    engine.lines_this_round = 10_000
    assert engine.tick_interval == MIN_TICK_RATE

    # New round -> back to base speed
    engine._reset_round()
    assert engine.speed_level == 0
    assert engine.tick_interval == TICK_RATE


def test_dormant_identity_restored_on_rejoin():
    engine = GameEngine(width=20)
    engine.add_player("p1", name="Andrew")
    engine.scores["p1"] = 700

    engine.remove_player("p1")
    assert "p1" not in engine.scores  # gone from the leaderboard
    assert engine.dormant["p1"] == {"name": "Andrew", "score": 700}

    engine.add_player("p1")  # same identity reconnects
    assert engine.names["p1"] == "Andrew"
    assert engine.scores["p1"] == 700
    assert "p1" not in engine.dormant  # consumed


def test_dormant_capped():
    from server.config import DORMANT_LIMIT

    engine = GameEngine(width=100)
    for i in range(DORMANT_LIMIT + 20):
        pid = f"p{i}"
        engine.add_player(pid)
        engine.remove_player(pid)
    assert len(engine.dormant) == DORMANT_LIMIT
    assert "p0" not in engine.dormant  # oldest evicted
    assert f"p{DORMANT_LIMIT + 19}" in engine.dormant


def test_leaderboard_sorted_and_capped():
    engine = GameEngine(width=100)
    for i in range(15):
        engine.add_player(f"p{i}", name=f"player{i}")
        engine.scores[f"p{i}"] = i * 10

    state = engine.get_state()
    board = state["leaderboard"]

    assert len(board) == 10  # capped at LEADERBOARD_SIZE
    scores = [entry["score"] for entry in board]
    assert scores == sorted(scores, reverse=True)
    assert board[0]["name"] == "player14"
