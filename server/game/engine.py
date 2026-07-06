"""Game engine — coordinates the board, all active pieces, and game state.

Each player has their own falling piece. Gravity moves ALL pieces down on each
tick. Players send actions (move/rotate/drop/hold) that are applied immediately.
When a piece can't move down, it locks into the board.

The game never permanently ends: when the board tops out, the grid is wiped
and a new round begins. Scores and players carry over across rounds.
"""

from __future__ import annotations

import random
from collections import deque

from ..config import (
    BOARD_HEIGHT,
    BOARD_MAX_WIDTH,
    BOARD_MIN_WIDTH,
    COLUMNS_PER_PLAYER,
    LEADERBOARD_SIZE,
    MAX_NAME_LENGTH,
    SPAWN_TOP_ROW,
)
from .board import Board
from .piece import get_cells, get_wall_kicks
from .types import Action, CellColor, PieceState, PieceType, Position


class Bag:
    """7-bag randomizer: shuffles all 7 piece types, deals them out, repeats.

    This ensures every player sees each piece type once per 7 pieces,
    preventing long droughts of any single piece.
    """

    def __init__(self) -> None:
        self._queue: deque[PieceType] = deque()

    def next(self) -> PieceType:
        if not self._queue:
            pieces = list(PieceType)
            random.shuffle(pieces)
            self._queue.extend(pieces)
        return self._queue.popleft()


class GameEngine:
    def __init__(self, width: int = BOARD_MIN_WIDTH, height: int = BOARD_HEIGHT):
        self.board = Board(width=width, height=height)
        self.active_pieces: dict[str, PieceState] = {}  # player_id -> PieceState
        self.bags: dict[str, Bag] = {}  # player_id -> their personal Bag
        self.next_pieces: dict[str, PieceType] = {}  # player_id -> next piece preview
        self.held_pieces: dict[str, PieceType | None] = {}  # player_id -> held piece
        self.hold_used: dict[str, bool] = {}  # player_id -> already held this piece?
        self.names: dict[str, str] = {}  # player_id -> display name
        self.scores: dict[str, int] = {}  # player_id -> personal score
        self.score: int = 0  # team score (sum of all points ever earned)
        self.lines_cleared: int = 0
        self.round: int = 1
        # Set when the board topped out and was wiped; popped into the next delta
        self._round_just_reset: bool = False
        # Delta tracking: cells that changed since last get_delta() call
        self._dirty_cells: set[tuple[int, int]] = set()
        self._prev_grid_width: int = width

    @property
    def player_count(self) -> int:
        return len(self.active_pieces)

    def desired_width(self, num_players: int) -> int:
        """Calculate the board width needed for the given number of players."""
        return max(BOARD_MIN_WIDTH, min(num_players * COLUMNS_PER_PLAYER, BOARD_MAX_WIDTH))

    def add_player(self, player_id: str, name: str | None = None) -> PieceState | None:
        """Add a player to the game and spawn their first piece."""
        # Expand board if needed
        new_width = self.desired_width(len(self.active_pieces) + 1)
        if new_width > self.board.width:
            self.board.expand_width(new_width)

        # Give the player their own bag and pre-generate next piece
        bag = Bag()
        self.bags[player_id] = bag
        self.next_pieces[player_id] = bag.next()
        self.held_pieces[player_id] = None
        self.hold_used[player_id] = False
        self.scores.setdefault(player_id, 0)
        self.set_name(player_id, name or f"player-{player_id[:4]}")

        return self.spawn_piece(player_id)

    def remove_player(self, player_id: str) -> None:
        """Remove a player and their active piece from the game."""
        self.active_pieces.pop(player_id, None)
        self.bags.pop(player_id, None)
        self.next_pieces.pop(player_id, None)
        self.held_pieces.pop(player_id, None)
        self.hold_used.pop(player_id, None)
        self.names.pop(player_id, None)
        self.scores.pop(player_id, None)

    def set_name(self, player_id: str, name: str) -> None:
        """Set a player's display name (trimmed, length-capped)."""
        cleaned = name.strip()[:MAX_NAME_LENGTH]
        if cleaned:
            self.names[player_id] = cleaned

    def spawn_piece(
        self, player_id: str, piece_type: PieceType | None = None
    ) -> PieceState | None:
        """Spawn a piece for the given player.

        Uses the player's next-piece queue unless an explicit type is given
        (hold swaps pass one). If no column on the board can fit the piece,
        the board is wiped (new round) and the spawn retried.
        """
        bag = self.bags.get(player_id)
        if bag is None:
            return None

        if piece_type is None:
            # Use the pre-generated next piece, then generate a new next
            piece_type = self.next_pieces.get(player_id) or bag.next()
            self.next_pieces[player_id] = bag.next()

        piece = self._find_spawn(piece_type)
        if piece is None:
            # Nowhere to spawn — the board is jammed at the top. New round.
            self._reset_round()
            piece = self._find_spawn(piece_type)
        if piece is None:
            # Only possible if the board is narrower than the piece itself
            return None

        self.active_pieces[player_id] = piece
        return piece

    def _find_spawn(self, piece_type: PieceType) -> PieceState | None:
        """Find a free spawn column: try a random one, then scan all columns."""
        max_col = max(0, self.board.width - 4)
        start = random.randint(0, max_col)
        # Try the random column first, then every column (wrapping around)
        for offset in range(max_col + 1):
            col = (start + offset) % (max_col + 1)
            piece = PieceState(
                piece_type=piece_type,
                position=Position(SPAWN_TOP_ROW, col),
                rotation=0,
            )
            if self.board.is_valid_position(piece):
                return piece
        return None

    def _reset_round(self) -> None:
        """Wipe the board and start a new round. Players and scores carry over."""
        for r in range(self.board.height):
            for c in range(self.board.width):
                self.board.grid[r][c] = CellColor.EMPTY
                self._dirty_cells.add((r, c))
        self.round += 1
        self._round_just_reset = True

    def process_action(self, player_id: str, action: Action) -> bool:
        """Process a player's action on their piece. Returns True if the action succeeded."""
        piece = self.active_pieces.get(player_id)
        if piece is None:
            return False

        if action == Action.MOVE_LEFT:
            return self._try_move(player_id, piece, 0, -1)
        elif action == Action.MOVE_RIGHT:
            return self._try_move(player_id, piece, 0, 1)
        elif action == Action.SOFT_DROP:
            return self._try_move(player_id, piece, 1, 0)
        elif action == Action.HARD_DROP:
            return self._hard_drop(player_id, piece)
        elif action == Action.ROTATE_CW:
            return self._try_rotate(player_id, piece, 1)
        elif action == Action.ROTATE_CCW:
            return self._try_rotate(player_id, piece, -1)
        elif action == Action.HOLD:
            return self._hold(player_id, piece)

        return False

    def _try_move(self, player_id: str, piece: PieceState, d_row: int, d_col: int) -> bool:
        """Try to move a piece by the given offset."""
        new_piece = piece.moved(d_row, d_col)
        if self.board.is_valid_position(new_piece):
            self.active_pieces[player_id] = new_piece
            return True
        return False

    def _try_rotate(self, player_id: str, piece: PieceState, direction: int) -> bool:
        """Try to rotate a piece, using wall kicks if needed."""
        new_piece = piece.rotated(direction)

        # Try the basic rotation first
        if self.board.is_valid_position(new_piece):
            self.active_pieces[player_id] = new_piece
            return True

        # Try wall kicks
        kicks = get_wall_kicks(piece.piece_type, piece.rotation, new_piece.rotation)
        for d_row, d_col in kicks:
            kicked = new_piece.moved(d_row, d_col)
            if self.board.is_valid_position(kicked):
                self.active_pieces[player_id] = kicked
                return True

        return False

    def _hold(self, player_id: str, piece: PieceState) -> bool:
        """Stash the current piece and swap in the held one (or the next piece).

        Only one hold is allowed per piece — the flag resets when a piece locks.
        """
        if self.hold_used.get(player_id):
            return False

        previously_held = self.held_pieces.get(player_id)
        self.held_pieces[player_id] = piece.piece_type
        self.hold_used[player_id] = True
        self.active_pieces.pop(player_id, None)

        if previously_held is not None:
            self.spawn_piece(player_id, piece_type=previously_held)
        else:
            self.spawn_piece(player_id)
        return True

    def _hard_drop(self, player_id: str, piece: PieceState) -> bool:
        """Drop a piece straight down until it can't go further, then lock it."""
        current = piece
        while True:
            next_pos = current.moved(1, 0)
            if not self.board.is_valid_position(next_pos):
                break
            current = next_pos

        self.active_pieces[player_id] = current
        self._lock_piece(player_id)
        return True

    def _lock_piece(self, player_id: str) -> None:
        """Lock a player's piece into the board, score any clears, spawn a new piece."""
        piece = self.active_pieces.get(player_id)
        if piece is None:
            return

        # Track locked cells as dirty
        for cell in get_cells(piece):
            self._dirty_cells.add((cell.row, cell.col))

        self.board.lock_piece(piece)

        cleared = self.board.clear_lines()
        if cleared > 0:
            self.lines_cleared += cleared
            points = {1: 100, 2: 300, 3: 500, 4: 800}
            earned = points.get(cleared, cleared * 200)
            self.score += earned
            # Credit the player whose piece completed the line(s)
            self.scores[player_id] = self.scores.get(player_id, 0) + earned
            # Line clear affects everything — mark entire board dirty
            for r in range(self.board.height):
                for c in range(self.board.width):
                    self._dirty_cells.add((r, c))

        # Locking finishes this piece — the player may hold again
        self.hold_used[player_id] = False

        if self.board.is_topped_out():
            self._reset_round()

        self.spawn_piece(player_id)

    def tick(self) -> None:
        """Apply gravity: move all active pieces down one row.

        Pieces that can't move down get locked into the board.
        """
        # Collect which players need to be locked (can't move down)
        to_lock: list[str] = []

        for player_id, piece in self.active_pieces.items():
            new_piece = piece.moved(1, 0)
            if self.board.is_valid_position(new_piece):
                self.active_pieces[player_id] = new_piece
            else:
                to_lock.append(player_id)

        # Lock pieces that couldn't move down
        for player_id in to_lock:
            self._lock_piece(player_id)

    def _ghost_position(self, piece: PieceState) -> PieceState:
        """Calculate where a piece would land if hard-dropped (ghost piece)."""
        current = piece
        while True:
            next_pos = current.moved(1, 0)
            if not self.board.is_valid_position(next_pos):
                return current
            current = next_pos

    def _build_active_pieces(self) -> dict:
        active = {}
        for player_id, piece in self.active_pieces.items():
            cells = get_cells(piece)
            ghost = self._ghost_position(piece)
            ghost_cells = get_cells(ghost)
            next_type = self.next_pieces.get(player_id)
            held_type = self.held_pieces.get(player_id)
            active[player_id] = {
                "piece_type": piece.piece_type.value,
                "cells": [{"row": c.row, "col": c.col} for c in cells],
                "ghost_cells": [{"row": c.row, "col": c.col} for c in ghost_cells],
                "rotation": piece.rotation,
                "next_piece": next_type.value if next_type else None,
                "held_piece": held_type.value if held_type else None,
                "name": self.names.get(player_id, ""),
                "score": self.scores.get(player_id, 0),
            }
        return active

    def _build_leaderboard(self) -> list[dict]:
        """Top players by personal score."""
        ranked = sorted(self.scores.items(), key=lambda kv: kv[1], reverse=True)
        return [
            {"id": pid, "name": self.names.get(pid, ""), "score": score}
            for pid, score in ranked[:LEADERBOARD_SIZE]
        ]

    def get_state(self) -> dict:
        """Full state snapshot (sent to new connections)."""
        return {
            "grid": self.board.get_grid_snapshot(),
            "active_pieces": self._build_active_pieces(),
            "score": self.score,
            "lines_cleared": self.lines_cleared,
            "board_width": self.board.width,
            "board_height": self.board.height,
            "player_count": self.player_count,
            "round": self.round,
            "leaderboard": self._build_leaderboard(),
        }

    def get_delta(self) -> dict:
        """Delta state — only changed grid cells + all active pieces.

        Returns a dict with 'grid_delta' (list of [row, col, color]) instead
        of the full grid. Also includes board_width if it changed.
        Clears the dirty set after building the delta.
        """
        delta: list[list[int]] = []
        for r, c in self._dirty_cells:
            if 0 <= r < self.board.height and 0 <= c < self.board.width:
                delta.append([r, c, int(self.board.grid[r][c])])
        self._dirty_cells.clear()

        result: dict = {
            "active_pieces": self._build_active_pieces(),
            "score": self.score,
            "lines_cleared": self.lines_cleared,
            "player_count": self.player_count,
            "round": self.round,
            "leaderboard": self._build_leaderboard(),
        }

        if delta:
            result["grid_delta"] = delta

        if self._round_just_reset:
            result["round_reset"] = True
            self._round_just_reset = False

        # If board expanded, tell the client
        if self.board.width != self._prev_grid_width:
            result["board_width"] = self.board.width
            result["board_height"] = self.board.height
            self._prev_grid_width = self.board.width

        return result
