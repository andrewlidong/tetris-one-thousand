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
        # Active piece collision map: (row, col) -> player_id who currently
        # occupies that cell. Used so other players' falling pieces collide
        # with each other instead of phasing through.
        self._active_cell_owners: dict[tuple[int, int], str] = {}

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

        # Expand board if needed. Counted from bags (every connected player)
        # rather than active_pieces (only those with a current piece) so the
        # board grows even when piece-on-piece collisions block some spawns.
        new_width = self.desired_width(len(self.bags) + 1)
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
        self._release_cells(player_id)
        self.active_pieces.pop(player_id, None)
        self.bags.pop(player_id, None)
        self.next_pieces.pop(player_id, None)

    def _release_cells(self, player_id: str) -> None:
        """Drop the player's current piece cells from the active collision map."""
        piece = self.active_pieces.get(player_id)
        if piece is None:
            return
        for cell in get_cells(piece):
            if self._active_cell_owners.get((cell.row, cell.col)) == player_id:
                del self._active_cell_owners[(cell.row, cell.col)]

    def _claim_cells(self, player_id: str, piece: PieceState) -> None:
        """Mark cells as occupied by player_id."""
        for cell in get_cells(piece):
            self._active_cell_owners[(cell.row, cell.col)] = player_id

    def _can_place(self, player_id: str, piece: PieceState) -> bool:
        """Can this piece occupy these cells right now? Checks board bounds,
        locked grid, and collisions with *other* players' active pieces.
        Caller is responsible for releasing this player's existing cells
        first (otherwise the piece will collide with itself).
        """
        if not self.board.is_valid_position(piece):
            return False
        for cell in get_cells(piece):
            owner = self._active_cell_owners.get((cell.row, cell.col))
            if owner is not None and owner != player_id:
                return False
        return True

    def _blocked_only_by_active(self, player_id: str, piece: PieceState) -> bool:
        """True if `piece` cannot be placed but every blocker is another
        player's active piece (no walls, no floor, no locked grid). Used so
        a piece resting on another active piece doesn't lock — instead it
        rides on top and falls when the supporter falls.
        """
        has_active_block = False
        for cell in get_cells(piece):
            if not self.board.in_bounds(cell):
                return False  # wall/floor block — must lock
            if self.board.grid[cell.row][cell.col] != 0:
                return False  # locked grid block — must lock
            owner = self._active_cell_owners.get((cell.row, cell.col))
            if owner is not None and owner != player_id:
                has_active_block = True
        return has_active_block

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
            if self._can_place(player_id, piece):
                self.next_pieces[player_id] = bag.next()
                self.active_pieces[player_id] = piece
                self._claim_cells(player_id, piece)
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

    def _carried_stack(self, player_id: str) -> list[str]:
        """All active pieces that rest on player_id's piece (transitively).

        Walks upward through the active-cell map: for each piece in the
        stack, the cell directly above each of its cells tells us who (if
        anyone) is sitting on it. O(stack-size × piece-size), not O(N).
        """
        stack = {player_id}
        queue = [player_id]
        while queue:
            pid = queue.pop()
            piece = self.active_pieces.get(pid)
            if piece is None:
                continue
            for cell in get_cells(piece):
                owner_above = self._active_cell_owners.get((cell.row - 1, cell.col))
                if owner_above is not None and owner_above not in stack:
                    stack.add(owner_above)
                    queue.append(owner_above)
        return list(stack)

    def _try_move(self, player_id: str, piece: PieceState, d_row: int, d_col: int) -> bool:
        """Try to move a piece by the given offset.

        Horizontal moves carry every piece resting on top of this one (and
        on those, transitively). Vertical moves only move the single piece.
        If any piece in the carried stack would collide, the whole move
        is rejected.
        """
        # Vertical moves (gravity / soft drop) only affect this piece.
        if d_col == 0:
            new_piece = piece.moved(d_row, d_col)
            self._release_cells(player_id)
            if self._can_place(player_id, new_piece):
                self.active_pieces[player_id] = new_piece
                self._claim_cells(player_id, new_piece)
                self._dirty_pieces.add(player_id)
                return True
            self._claim_cells(player_id, piece)
            return False

        # Horizontal move: also drag everything stacked on top.
        stack_ids = self._carried_stack(player_id)
        old_pieces = {pid: self.active_pieces[pid] for pid in stack_ids}
        for pid in stack_ids:
            self._release_cells(pid)

        # Validate every piece in the stack at its new position. With all
        # stack cells released, _can_place only sees walls, locked grid,
        # and active pieces *outside* the stack.
        new_pieces = {pid: old.moved(d_row, d_col) for pid, old in old_pieces.items()}
        if not all(self._can_place(pid, np) for pid, np in new_pieces.items()):
            for pid, old in old_pieces.items():
                self._claim_cells(pid, old)
            return False

        for pid, np in new_pieces.items():
            self.active_pieces[pid] = np
            self._claim_cells(pid, np)
            self._dirty_pieces.add(pid)
        return True

    def _try_rotate(self, player_id: str, piece: PieceState, direction: int) -> bool:
        """Try to rotate a piece, using wall kicks if needed."""
        new_piece = piece.rotated(direction)
        self._release_cells(player_id)

        candidates = [new_piece]
        for dr, dc in get_wall_kicks(piece.piece_type, piece.rotation, new_piece.rotation):
            candidates.append(new_piece.moved(dr, dc))

        for candidate in candidates:
            if self._can_place(player_id, candidate):
                self.active_pieces[player_id] = candidate
                self._claim_cells(player_id, candidate)
                self._dirty_pieces.add(player_id)
                return True

        # All rotations blocked — restore original
        self._claim_cells(player_id, piece)
        return False

    def _hard_drop(self, player_id: str, piece: PieceState) -> bool:
        """Drop a piece straight down until it can't go further. Locks if it
        landed on the floor or a locked cell; otherwise rests on the active
        piece below and will fall with it on the next tick.
        """
        self._release_cells(player_id)
        current = piece
        while True:
            next_pos = current.moved(1, 0)
            if not self._can_place(player_id, next_pos):
                break
            current = next_pos

        self.active_pieces[player_id] = current
        self._claim_cells(player_id, current)
        self._dirty_pieces.add(player_id)
        # Don't lock if the only thing stopping us is another active piece.
        below = current.moved(1, 0)
        if not self._blocked_only_by_active(player_id, below):
            self._lock_piece(player_id)
        return True

    def _lock_piece(self, player_id: str) -> None:
        """Lock a player's piece into the board and spawn a new one."""
        piece = self.active_pieces.get(player_id)
        if piece is None:
            return

        # The piece's cells move from "active" (collision via _active_cell_owners)
        # to "locked" (collision via the board grid).
        self._release_cells(player_id)
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

        Bottom-most pieces are processed first so a stack of falling pieces
        can all advance in one tick — otherwise the lowest piece would block
        the one above it on this tick, locking it prematurely.
        """
        # Sort by bottom row of each piece, descending
        order = sorted(
            self.active_pieces.items(),
            key=lambda kv: max(c.row for c in get_cells(kv[1])),
            reverse=True,
        )

        to_lock: list[str] = []
        for player_id, piece in order:
            new_piece = piece.moved(1, 0)
            self._release_cells(player_id)
            if self._can_place(player_id, new_piece):
                self.active_pieces[player_id] = new_piece
                self._claim_cells(player_id, new_piece)
                self._dirty_pieces.add(player_id)
            else:
                self._claim_cells(player_id, piece)
                # Only lock if we hit something solid. If we're resting on
                # another active piece, wait — it may fall this tick or next.
                if not self._blocked_only_by_active(player_id, new_piece):
                    to_lock.append(player_id)

        # Lock pieces that couldn't move down
        for player_id in to_lock:
            self._lock_piece(player_id)

        # Retry spawning for any waiting players (blocked from spawning earlier)
        for player_id in list(self.bags):
            if player_id not in self.active_pieces:
                self.spawn_piece(player_id)

    def _ghost_position(self, player_id: str, piece: PieceState) -> PieceState:
        """Calculate where a piece would land if hard-dropped (ghost piece).
        Stops at other players' active pieces too, not just the locked grid.
        """
        current = piece
        while True:
            next_pos = current.moved(1, 0)
            if not self._can_place(player_id, next_pos):
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
            ghost = self._ghost_position(player_id, piece)
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
