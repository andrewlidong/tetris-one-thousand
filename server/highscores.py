"""Persistent all-time high scores, stored as a small JSON file.

Keeps the best score per player name, top N overall. Writes are atomic
(tmp file + rename) and only happen when the table actually changes.

Note: on hosts with ephemeral disks (e.g. Render's free tier) the file
resets on redeploy — accepted for now.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

HIGHSCORE_LIMIT = 10


class HighScores:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.environ.get("HIGHSCORE_FILE", "highscores.json"))
        self._table: list[dict] = []
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
            if isinstance(data, list):
                self._table = [
                    {"name": str(e["name"]), "score": int(e["score"])}
                    for e in data
                    if isinstance(e, dict) and "name" in e and "score" in e
                ]
        except (OSError, ValueError, KeyError, TypeError):
            self._table = []

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._table, indent=2))
            tmp.replace(self.path)
        except OSError:
            pass  # a read-only disk shouldn't take the game down

    def submit(self, name: str, score: int) -> bool:
        """Record a score. Returns True if the table changed."""
        if score <= 0 or not name:
            return False

        for entry in self._table:
            if entry["name"] == name:
                if score <= entry["score"]:
                    return False
                entry["score"] = score
                break
        else:
            self._table.append({"name": name, "score": score})

        self._table.sort(key=lambda e: e["score"], reverse=True)
        del self._table[HIGHSCORE_LIMIT:]

        # The new/updated entry may have been trimmed right back off
        if not any(e["name"] == name and e["score"] == score for e in self._table):
            return False

        self._save()
        return True

    def top(self, n: int = HIGHSCORE_LIMIT) -> list[dict]:
        return self._table[:n]
