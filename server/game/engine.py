"""Game engine — coordinates the board, all active pieces, and game state.

Each player has their own falling piece. Gravity moves ALL pieces down on each
tick. Players send actions (move/rotate/drop) that are applied immediately.
When a piece can't move down, it locks into the board.
"""

from __future__ import annotations

import random
from collections import deque

from ..config import (
    BOARD_HEIGHT,
    BOARD_MAX_WIDTH,
    BOARD_MIN_WIDTH,
    COLUMNS_PER_PLAYER,
    SPAWN_TOP_ROW,
)
from .board import Board
from .piece import get_cells, get_wall_kicks
from .types import Action, PieceState, PieceType, Position


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
        self.score: int = 0
        self.lines_cleared: int = 0
        self.game_over: bool = False
        # Delta tracking: cells / pieces that changed since last get_delta() call
        self._dirty_cells: set[tuple[int, int]] = set()
        self._dirty_pieces: set[str] = set()
        self._removed_players: set[str] = set()
        self._prev_grid_width: int = width

    @property
    def player_count(self) -> int:
        return len(self.active_pieces)

    def desired_width(self, num_players: int) -> int:
        """Calculate the board width needed for the given number of players."""
        return max(BOARD_MIN_WIDTH, min(num_players * COLUMNS_PER_PLAYER, BOARD_MAX_WIDTH))

    def add_player(self, player_id: str) -> PieceState | None:
        """Add a player to the game. Returns their spawned piece, or None if game over."""
        if self.game_over:
            return None

        # Expand board if needed
        new_width = self.desired_width(len(self.active_pieces) + 1)
        if new_width > self.board.width:
            self.board.expand_width(new_width)

        # Give the player their own bag and pre-generate next piece
        bag = Bag()
        self.bags[player_id] = bag
        self.next_pieces[player_id] = bag.next()

        return self.spawn_piece(player_id)

    def remove_player(self, player_id: str) -> None:
        """Remove a player and their active piece from the game."""
        if player_id in self.active_pieces or player_id in self.bags:
            self._removed_players.add(player_id)
            self._dirty_pieces.discard(player_id)
        self.active_pieces.pop(player_id, None)
        self.bags.pop(player_id, None)
        self.next_pieces.pop(player_id, None)

    def spawn_piece(self, player_id: str) -> PieceState | None:
        """Spawn a new piece for the given player at a spread-out column.

        Tries a few random columns to find a clear spawn slot. If all are
        blocked, returns None — the player will just be without a piece for
        this tick, and the gravity loop will retry next tick. No global game
        over: one player's spawn problem doesn't freeze a 1000-player session.
        """
        bag = self.bags.get(player_id)
        if bag is None:
            return None

        max_col = max(0, self.board.width - 4)
        # Try the pre-generated piece at several random columns first.
        piece_type = self.next_pieces.get(player_id, bag.next())
        for _ in range(5):
            col = random.randint(0, max_col)
            piece = PieceState(
                piece_type=piece_type,
                position=Position(SPAWN_TOP_ROW, col),
                rotation=0,
            )
            if self.board.is_valid_position(piece):
                self.next_pieces[player_id] = bag.next()
                self.active_pieces[player_id] = piece
                self._dirty_pieces.add(player_id)
                return piece

        return None

    def process_action(self, player_id: str, action: Action) -> bool:
        """Process a player's action on their piece. Returns True if the action succeeded."""
        piece = self.active_pieces.get(player_id)
        if piece is None or self.game_over:
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

        return False

    def _try_move(self, player_id: str, piece: PieceState, d_row: int, d_col: int) -> bool:
        """Try to move a piece by the given offset."""
        new_piece = piece.moved(d_row, d_col)
        if self.board.is_valid_position(new_piece):
            self.active_pieces[player_id] = new_piece
            self._dirty_pieces.add(player_id)
            return True
        return False

    def _try_rotate(self, player_id: str, piece: PieceState, direction: int) -> bool:
        """Try to rotate a piece, using wall kicks if needed."""
        new_piece = piece.rotated(direction)

        # Try the basic rotation first
        if self.board.is_valid_position(new_piece):
            self.active_pieces[player_id] = new_piece
            self._dirty_pieces.add(player_id)
            return True

        # Try wall kicks
        kicks = get_wall_kicks(piece.piece_type, piece.rotation, new_piece.rotation)
        for d_row, d_col in kicks:
            kicked = new_piece.moved(d_row, d_col)
            if self.board.is_valid_position(kicked):
                self.active_pieces[player_id] = kicked
                self._dirty_pieces.add(player_id)
                return True

        return False

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
        """Lock a player's piece into the board and spawn a new one."""
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
            self.score += points.get(cleared, cleared * 200)
            # Line clear affects everything — mark entire board dirty
            for r in range(self.board.height):
                for c in range(self.board.width):
                    self._dirty_cells.add((r, c))

        # Try to spawn a new piece. If blocked (board full at the top), the
        # player just sits this tick out — the gravity loop retries next tick.
        self.active_pieces.pop(player_id, None)
        self.spawn_piece(player_id)

    def tick(self) -> None:
        """Apply gravity: move all active pieces down one row.

        Pieces that can't move down get locked into the board. Players who
        are missing an active piece (because their last spawn was blocked)
        get a retry attempt.
        """
        # Collect which players need to be locked (can't move down)
        to_lock: list[str] = []

        for player_id, piece in self.active_pieces.items():
            new_piece = piece.moved(1, 0)
            if self.board.is_valid_position(new_piece):
                self.active_pieces[player_id] = new_piece
                self._dirty_pieces.add(player_id)
            else:
                to_lock.append(player_id)

        # Lock pieces that couldn't move down
        for player_id in to_lock:
            self._lock_piece(player_id)

        # Retry spawning for any waiting players (blocked from spawning earlier)
        for player_id in list(self.bags):
            if player_id not in self.active_pieces:
                self.spawn_piece(player_id)

    def _ghost_position(self, piece: PieceState) -> PieceState:
        """Calculate where a piece would land if hard-dropped (ghost piece)."""
        current = piece
        while True:
            next_pos = current.moved(1, 0)
            if not self.board.is_valid_position(next_pos):
                return current
            current = next_pos

    def piece_payload(self, player_id: str, piece: PieceState, include_ghost: bool = False) -> dict:
        cells = get_cells(piece)
        next_type = self.next_pieces.get(player_id)
        payload = {
            "piece_type": piece.piece_type.value,
            "cells": [{"row": c.row, "col": c.col} for c in cells],
            "rotation": piece.rotation,
            "next_piece": next_type.value if next_type else None,
        }
        if include_ghost:
            ghost = self._ghost_position(piece)
            payload["ghost_cells"] = [{"row": c.row, "col": c.col} for c in get_cells(ghost)]
        return payload

    def _build_active_pieces(self, player_ids=None, include_ghost: bool = False) -> dict:
        """Build active piece payloads. Ghost cells are only rendered for the
        local player, so by default they're omitted from broadcast deltas to
        save 30+ collision checks per piece per tick.
        """
        ids = player_ids if player_ids is not None else self.active_pieces.keys()
        active = {}
        for player_id in ids:
            piece = self.active_pieces.get(player_id)
            if piece is None:
                continue
            active[player_id] = self.piece_payload(player_id, piece, include_ghost=include_ghost)
        return active

    def get_state(self) -> dict:
        """Full state snapshot (sent to new connections)."""
        return {
            "grid": self.board.get_grid_snapshot(),
            "active_pieces": self._build_active_pieces(include_ghost=True),
            "score": self.score,
            "lines_cleared": self.lines_cleared,
            "board_width": self.board.width,
            "board_height": self.board.height,
            "player_count": self.player_count,
            "game_over": self.game_over,
        }

    def get_delta(self) -> dict | None:
        """Delta state — only what changed since last call.

        Includes:
          - 'grid_delta': list of [row, col, color] for changed cells
          - 'pieces_delta': dict of player_id -> piece payload, only changed pieces
          - 'removed_pieces': list of player_ids whose pieces should be dropped
        Returns None if nothing changed (so the broadcast loop can skip the send).
        """
        cells: list[list[int]] = []
        for r, c in self._dirty_cells:
            if 0 <= r < self.board.height and 0 <= c < self.board.width:
                cells.append([r, c, int(self.board.grid[r][c])])
        self._dirty_cells.clear()

        pieces = self._build_active_pieces(self._dirty_pieces)
        removed = list(self._removed_players)
        self._dirty_pieces.clear()
        self._removed_players.clear()

        width_changed = self.board.width != self._prev_grid_width

        if not cells and not pieces and not removed and not width_changed:
            return None

        result: dict = {
            "score": self.score,
            "lines_cleared": self.lines_cleared,
            "player_count": self.player_count,
            "game_over": self.game_over,
        }
        if cells:
            result["grid_delta"] = cells
        if pieces:
            result["pieces_delta"] = pieces
        if removed:
            result["removed_pieces"] = removed
        if width_changed:
            result["board_width"] = self.board.width
            result["board_height"] = self.board.height
            self._prev_grid_width = self.board.width

        return result
