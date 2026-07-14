import json

from server.highscores import HIGHSCORE_LIMIT, HighScores


def test_submit_and_top(tmp_path):
    hs = HighScores(tmp_path / "hs.json")
    assert hs.submit("Andrew", 500) is True
    assert hs.submit("Rival", 300) is True
    assert hs.top() == [
        {"name": "Andrew", "score": 500},
        {"name": "Rival", "score": 300},
    ]


def test_best_score_per_name(tmp_path):
    hs = HighScores(tmp_path / "hs.json")
    hs.submit("Andrew", 500)
    assert hs.submit("Andrew", 200) is False  # worse -> ignored
    assert hs.submit("Andrew", 900) is True  # better -> updated
    assert hs.top() == [{"name": "Andrew", "score": 900}]


def test_zero_and_blank_rejected(tmp_path):
    hs = HighScores(tmp_path / "hs.json")
    assert hs.submit("Andrew", 0) is False
    assert hs.submit("", 100) is False
    assert hs.top() == []


def test_table_capped(tmp_path):
    hs = HighScores(tmp_path / "hs.json")
    for i in range(HIGHSCORE_LIMIT + 5):
        hs.submit(f"p{i}", (i + 1) * 100)
    assert len(hs.top()) == HIGHSCORE_LIMIT
    # A score too low for the table is rejected
    assert hs.submit("loser", 1) is False


def test_persists_across_instances(tmp_path):
    path = tmp_path / "hs.json"
    HighScores(path).submit("Andrew", 800)

    reloaded = HighScores(path)
    assert reloaded.top() == [{"name": "Andrew", "score": 800}]


def test_corrupt_file_ignored(tmp_path):
    path = tmp_path / "hs.json"
    path.write_text("{not json!")
    hs = HighScores(path)
    assert hs.top() == []
    hs.submit("Andrew", 100)
    assert json.loads(path.read_text()) == [{"name": "Andrew", "score": 100}]
