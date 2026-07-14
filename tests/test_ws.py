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

        # Should receive full state on connect
        state = ws.receive_json()
        assert state["type"] == "state"
        assert "grid" in state
        assert state["player_count"] >= 1


def _consume_connect(ws):
    """Consume the welcome, full state, and connect delta messages."""
    welcome = ws.receive_json()
    assert welcome["type"] == "welcome"
    state = ws.receive_json()
    assert state["type"] == "state"
    delta = ws.receive_json()
    assert delta["type"] == "delta"
    return welcome, state


def test_websocket_send_action():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        _consume_connect(ws)

        # soft_drop always succeeds right after spawn (left/right can fail at
        # a wall, and failed actions no longer broadcast)
        ws.send_json({"action": "soft_drop"})
        msg = ws.receive_json()
        assert msg["type"] == "delta"
        assert "active_pieces" in msg


def test_websocket_hard_drop():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        _consume_connect(ws)

        ws.send_json({"action": "hard_drop"})
        msg = ws.receive_json()
        assert msg["type"] == "delta"
        assert "grid_delta" in msg


def test_websocket_invalid_action_ignored():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        _consume_connect(ws)

        ws.send_json({"action": "invalid_action"})
        ws.send_json({"action": "soft_drop"})
        msg = ws.receive_json()
        assert msg["type"] == "delta"


def test_two_players():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        _consume_connect(ws1)

        with client.websocket_connect("/ws") as ws2:
            welcome2, state2 = _consume_connect(ws2)
            assert state2["player_count"] == 2

            # ws1 gets a delta when ws2 joins
            delta = ws1.receive_json()
            assert delta["type"] == "delta"
            assert delta["player_count"] == 2


def test_set_name_reflected_in_leaderboard():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        welcome, _ = _consume_connect(ws)
        my_id = welcome["player_id"]

        ws.send_json({"name": "Andrew"})
        msg = ws.receive_json()
        assert msg["type"] == "delta"
        names = {e["id"]: e["name"] for e in msg["leaderboard"]}
        assert names[my_id] == "Andrew"


def test_hold_action():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        welcome, _ = _consume_connect(ws)
        my_id = welcome["player_id"]

        ws.send_json({"action": "hold"})
        msg = ws.receive_json()
        assert msg["type"] == "delta"
        assert msg["active_pieces"][my_id]["held_piece"] is not None


def test_full_state_has_ghost_and_next():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # welcome
        state = ws.receive_json()  # full state
        assert state["type"] == "state"

        for pid, p in state["active_pieces"].items():
            assert "ghost_cells" in p
            assert "next_piece" in p
            assert len(p["ghost_cells"]) == 4
