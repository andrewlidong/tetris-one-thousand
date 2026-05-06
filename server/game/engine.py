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
        # Delta tracking: cells that changed since last get_delta() call
        self._dirty_cells: set[tuple[int, int]] = set()
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
        self.active_pieces.pop(player_id, None)
        self.bags.pop(player_id, None)
        self.next_pieces.pop(player_id, None)

    def spawn_piece(self, player_id: str) -> PieceState | None:
        """Spawn a new piece for the given player at a spread-out column."""
        if self.game_over:
            return None

        bag = self.bags.get(player_id)
        if bag is None:
            return None

        # Use the pre-generated next piece, then generate a new next
        piece_type = self.next_pieces.get(player_id, bag.next())
        self.next_pieces[player_id] = bag.next()

        # Pick a random spawn column, leaving room for the piece (max width 4)
        max_col = max(0, self.board.width - 4)
        col = random.randint(0, max_col)

        piece = PieceState(
            piece_type=piece_type,
            position=Position(SPAWN_TOP_ROW, col),
            rotation=0,
        )

        # If the spawn position is blocked, the game is over
        if not self.board.is_valid_position(piece):
            self.game_over = True
            return None

        self.active_pieces[player_id] = piece
        return piece

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

        if self.board.is_topped_out():
            self.game_over = True
            self.active_pieces.pop(player_id, None)
            return

        self.spawn_piece(player_id)

    def tick(self) -> None:
        """Apply gravity: move all active pieces down one row.

        Pieces that can't move down get locked into the board.
        """
        if self.game_over:
            return

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
            active[player_id] = {
                "piece_type": piece.piece_type.value,
                "cells": [{"row": c.row, "col": c.col} for c in cells],
                "ghost_cells": [{"row": c.row, "col": c.col} for c in ghost_cells],
                "rotation": piece.rotation,
                "next_piece": next_type.value if next_type else None,
            }
        return active

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
            "game_over": self.game_over,
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
            "game_over": self.game_over,
        }

        if delta:
            result["grid_delta"] = delta

        # If board expanded, tell the client
        if self.board.width != self._prev_grid_width:
            result["board_width"] = self.board.width
            result["board_height"] = self.board.height
            self._prev_grid_width = self.board.width

        return result
