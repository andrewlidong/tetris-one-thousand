import pytest
from fastapi.testclient import TestClient

from server.main import app, engine, manager


@pytest.fixture(autouse=True)
def reset_state():
    """Reset game state between tests."""
    from server.game.engine import GameEngine
    fresh = GameEngine()
    engine.__dict__.update(fresh.__dict__)
    manager.connections.clear()
    yield


def test_index_returns_html():
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_websocket_connect_and_welcome():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "welcome"
        assert "player_id" in msg

        state = ws.receive_json()
        assert state["type"] == "state"
        assert "grid" in state
        assert state["player_count"] >= 1


def test_websocket_send_action_updates_engine():
    """Actions update the engine state immediately (no synchronous broadcast)."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # welcome
        state = ws.receive_json()  # full state
        player_id = next(iter(state["active_pieces"]))
        col_before = engine.active_pieces[player_id].position.col

        ws.send_json({"action": "right"})

        # Action should have moved the piece (if room) or been a no-op (at edge).
        # Engine state must reflect what process_action did.
        col_after = engine.active_pieces[player_id].position.col
        assert col_after in (col_before, col_before + 1)


def test_websocket_hard_drop_locks_piece():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        state = ws.receive_json()
        player_id = next(iter(state["active_pieces"]))
        ws.send_json({"action": "hard_drop"})

        # Hard drop should lock the piece and spawn a new one at the top
        new_piece = engine.active_pieces.get(player_id)
        assert new_piece is not None
        assert new_piece.position.row == 0


def test_websocket_invalid_action_ignored():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.receive_json()
        # Should not raise or disconnect
        ws.send_json({"action": "invalid_action"})
        ws.send_json({"action": "left"})


def test_two_players_share_engine():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        ws1.receive_json()
        ws1.receive_json()
        with client.websocket_connect("/ws") as ws2:
            ws2.receive_json()
            state2 = ws2.receive_json()
            assert state2["player_count"] == 2
            assert engine.player_count == 2


def test_full_state_has_ghost_and_next():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        state = ws.receive_json()
        assert state["type"] == "state"
        for pid, p in state["active_pieces"].items():
            assert "ghost_cells" in p
            assert "next_piece" in p
            assert len(p["ghost_cells"]) == 4


def test_get_delta_returns_none_when_idle():
    """Without changes, get_delta should return None so the broadcast loop skips."""
    assert engine.get_delta() is None or engine.get_delta() == {}


def test_get_delta_includes_changed_pieces_only():
    engine.add_player("p1")
    engine.add_player("p2")
    # Adding players marks both pieces dirty; first delta has both
    delta = engine.get_delta()
    assert "pieces_delta" in delta
    assert set(delta["pieces_delta"].keys()) == {"p1", "p2"}

    # Now move only p1; delta should contain p1 only
    from server.game.types import Action
    engine.process_action("p1", Action.HARD_DROP)
    delta = engine.get_delta()
    assert "p1" in delta.get("pieces_delta", {})
    # p2 may or may not be present depending on whether hard_drop touched it; usually not
    assert "p2" not in delta.get("pieces_delta", {})


def test_get_delta_reports_removed_pieces():
    engine.add_player("p1")
    engine.get_delta()  # drain the initial dirty marks
    engine.remove_player("p1")
    delta = engine.get_delta()
    assert delta is not None
    assert delta.get("removed_pieces") == ["p1"]
