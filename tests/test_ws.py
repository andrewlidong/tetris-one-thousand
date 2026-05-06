import pytest
from fastapi.testclient import TestClient

from server.main import app, engine, manager


@pytest.fixture(autouse=True)
def reset_state():
    """Reset game state between tests."""
    engine.__init__()  # type: ignore[misc]
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

        # Should also receive initial state
        state = ws.receive_json()
        assert state["type"] == "state"
        assert state["player_count"] >= 1


def test_websocket_send_action():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        # Consume welcome + initial state
        ws.receive_json()  # welcome
        ws.receive_json()  # state

        # Send a move action
        ws.send_json({"action": "left"})
        state = ws.receive_json()
        assert state["type"] == "state"


def test_websocket_hard_drop():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # welcome
        ws.receive_json()  # state

        ws.send_json({"action": "hard_drop"})
        state = ws.receive_json()
        assert state["type"] == "state"
        # After hard drop, piece should have locked (score may or may not change)


def test_websocket_invalid_action_ignored():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # welcome
        ws.receive_json()  # state

        # Send garbage — should not crash
        ws.send_json({"action": "invalid_action"})
        # Send a valid action to confirm connection still works
        ws.send_json({"action": "left"})
        state = ws.receive_json()
        assert state["type"] == "state"


def test_two_players():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws1:
        welcome1 = ws1.receive_json()
        ws1.receive_json()  # state

        with client.websocket_connect("/ws") as ws2:
            welcome2 = ws2.receive_json()

            assert welcome1["player_id"] != welcome2["player_id"]

            # ws1 should also receive a state broadcast when ws2 joins
            state = ws1.receive_json()
            assert state["player_count"] == 2
