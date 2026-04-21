"""Game state machine: spawn, hold, gravity, lock delay, scoring, T-spin, levels."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from .bag import Bag
from .board import Board
from .constants import (
    B2B_MULT,
    BUFFER_ROWS,
    COLS,
    COMBO_BONUS,
    HARD_DROP_POINTS_PER_CELL,
    LINES_PER_LEVEL,
    LOCK_DELAY_MS,
    LOCK_RESET_CAP,
    SCORE_DOUBLE,
    SCORE_SINGLE,
    SCORE_TETRIS,
    SCORE_TRIPLE,
    SCORE_TSPIN,
    SCORE_TSPIN_DOUBLE,
    SCORE_TSPIN_MINI,
    SCORE_TSPIN_MINI_SINGLE,
    SCORE_TSPIN_SINGLE,
    SCORE_TSPIN_TRIPLE,
    SOFT_DROP_MULT,
    SOFT_DROP_POINTS_PER_CELL,
    gravity_ms_for_level,
)
from .pieces import BBOX_SIZE, Tetromino, kicks_for


class Phase(Enum):
    PLAYING = auto()
    PAUSED = auto()
    GAME_OVER = auto()


class TSpinKind(Enum):
    NONE = auto()
    MINI = auto()
    FULL = auto()


@dataclass
class LastClear:
    lines: int = 0
    tspin: TSpinKind = TSpinKind.NONE
    b2b: bool = False
    combo: int = 0
    points: int = 0


class GameState:
    def __init__(self, seed: int | None = None) -> None:
        import random

        rng = random.Random(seed) if seed is not None else random.Random()
        self.board = Board()
        self.bag = Bag(rng)
        self.phase = Phase.PLAYING
        self.active: Tetromino | None = None
        self.hold: str | None = None
        self.hold_used_this_turn = False

        self.score = 0
        self.lines = 0
        self.level = 1
        self.combo = -1  # -1 means no combo
        self.back_to_back = False
        self.last_clear = LastClear()

        self.soft_dropping = False
        self.gravity_accum_ms = 0.0
        self.lock_timer_ms = 0.0
        self.lock_resets = 0
        self.on_ground = False
        self.flash_rows: list[int] = []
        self.flash_timer_ms = 0.0

        self._spawn_next()

    # ----- spawning / hold -----
    def _spawn(self, kind: str) -> None:
        # Spawn position: columns 3-6, starting just inside the buffer so piece
        # appears at the top of the visible field after one gravity tick.
        bbox = BBOX_SIZE[kind]
        spawn_x = (COLS - bbox) // 2
        spawn_y = BUFFER_ROWS - 2  # piece top sits 2 rows above visible top
        piece = Tetromino(kind=kind, x=spawn_x, y=spawn_y, rot=0)
        # Top-out: if piece can't be placed at spawn, game over.
        if self.board.collides(piece):
            self.active = piece
            self.phase = Phase.GAME_OVER
            return
        self.active = piece
        self.hold_used_this_turn = False
        self.gravity_accum_ms = 0.0
        self.lock_timer_ms = 0.0
        self.lock_resets = 0
        self.on_ground = False

    def _spawn_next(self) -> None:
        self._spawn(self.bag.next())

    def hold_piece(self) -> None:
        if self.phase != Phase.PLAYING or self.active is None or self.hold_used_this_turn:
            return
        current_kind = self.active.kind
        if self.hold is None:
            self.hold = current_kind
            self._spawn_next()
        else:
            swap = self.hold
            self.hold = current_kind
            self._spawn(swap)
        self.hold_used_this_turn = True

    # ----- movement -----
    def try_move(self, dx: int, dy: int) -> bool:
        if self.active is None or self.phase != Phase.PLAYING:
            return False
        if not self.board.collides(self.active, dx=dx, dy=dy):
            self.active.x += dx
            self.active.y += dy
            self.active.last_move_was_rotate = False
            self._on_successful_move()
            return True
        return False

    def try_rotate(self, direction: int) -> bool:
        """direction: +1 for CW, -1 for CCW."""
        if self.active is None or self.phase != Phase.PLAYING:
            return False
        from_rot = self.active.rot
        to_rot = (from_rot + direction) % 4
        for i, (kx, ky) in enumerate(kicks_for(self.active.kind, from_rot, to_rot)):
            if not self.board.collides(self.active, rot=to_rot, dx=kx, dy=ky):
                self.active.x += kx
                self.active.y += ky
                self.active.rot = to_rot
                self.active.last_move_was_rotate = True
                self.active.last_kick_index = i
                self._on_successful_move()
                return True
        return False

    def _on_successful_move(self) -> None:
        """Reset lock-delay if the piece is resting on the ground and moved."""
        if self.on_ground and self.lock_resets < LOCK_RESET_CAP:
            self.lock_timer_ms = 0.0
            self.lock_resets += 1
        self._update_on_ground()

    def _update_on_ground(self) -> None:
        if self.active is None:
            return
        self.on_ground = self.board.collides(self.active, dy=1)

    # ----- drops -----
    def soft_drop_step(self) -> None:
        if self.try_move(0, 1):
            self.score += SOFT_DROP_POINTS_PER_CELL

    def hard_drop(self) -> None:
        if self.active is None or self.phase != Phase.PLAYING:
            return
        dropped = 0
        while not self.board.collides(self.active, dy=1):
            self.active.y += 1
            dropped += 1
        self.score += dropped * HARD_DROP_POINTS_PER_CELL
        self.active.last_move_was_rotate = False
        self._lock_piece()

    def ghost_offset(self) -> int:
        """How many rows below the active piece the ghost sits."""
        if self.active is None:
            return 0
        dy = 0
        while not self.board.collides(self.active, dy=dy + 1):
            dy += 1
        return dy

    # ----- locking -----
    def _lock_piece(self) -> None:
        assert self.active is not None
        t_spin = self._detect_t_spin(self.active)
        self.board.lock(self.active)
        cleared_rows = self.board.clear_lines()
        n = len(cleared_rows)
        self.flash_rows = cleared_rows
        self.flash_timer_ms = 120.0

        points, difficult = self._score_clear(n, t_spin)
        if n > 0:
            self.combo = self.combo + 1 if self.combo >= 0 else 0
            if self.combo > 0:
                points += COMBO_BONUS * self.combo * self.level
            # Back-to-back: only tetrises and T-spin-with-clear count as "difficult"
            if difficult:
                if self.back_to_back:
                    points = int(points * B2B_MULT)
                self.back_to_back = True
            else:
                self.back_to_back = False
        else:
            self.combo = -1
            # No line clear → B2B flag unchanged.

        self.score += points
        self.lines += n
        self.level = 1 + self.lines // LINES_PER_LEVEL

        self.last_clear = LastClear(
            lines=n,
            tspin=t_spin,
            b2b=difficult and self.back_to_back,
            combo=max(0, self.combo),
            points=points,
        )

        # Lock-out check: if the locked piece was entirely above the visible playfield,
        # game over.
        if self.active is not None and not self.board.piece_in_playfield(self.active):
            # Undo flash; game over.
            self.phase = Phase.GAME_OVER
            return

        self._spawn_next()

    def _detect_t_spin(self, piece: Tetromino) -> TSpinKind:
        if piece.kind != "T" or not piece.last_move_was_rotate:
            return TSpinKind.NONE
        total, front = self.board.t_spin_corners(piece)
        if total < 3:
            return TSpinKind.NONE
        # Full T-spin if both front corners are filled; otherwise mini.
        if front == 2:
            return TSpinKind.FULL
        # Exception: if the rotation used the 5th (last) kick, promote mini to full.
        if piece.last_kick_index == 4:
            return TSpinKind.FULL
        return TSpinKind.MINI

    def _score_clear(self, n: int, t_spin: TSpinKind) -> tuple[int, bool]:
        """Return (base_points, is_difficult)."""
        level = self.level
        if t_spin == TSpinKind.FULL:
            base = {
                0: SCORE_TSPIN,
                1: SCORE_TSPIN_SINGLE,
                2: SCORE_TSPIN_DOUBLE,
                3: SCORE_TSPIN_TRIPLE,
            }.get(n, 0)
            return (base * level, n > 0)
        if t_spin == TSpinKind.MINI:
            base = {0: SCORE_TSPIN_MINI, 1: SCORE_TSPIN_MINI_SINGLE}.get(n, 0)
            return (base * level, n > 0)
        base = {0: 0, 1: SCORE_SINGLE, 2: SCORE_DOUBLE, 3: SCORE_TRIPLE, 4: SCORE_TETRIS}[n]
        return (base * level, n == 4)

    # ----- update tick -----
    def update(self, dt_ms: float) -> None:
        if self.phase != Phase.PLAYING or self.active is None:
            return

        if self.flash_timer_ms > 0:
            self.flash_timer_ms = max(0.0, self.flash_timer_ms - dt_ms)

        self._update_on_ground()

        grav_ms = gravity_ms_for_level(self.level)
        if self.soft_dropping:
            grav_ms = max(1.0, grav_ms / SOFT_DROP_MULT)

        self.gravity_accum_ms += dt_ms
        while self.gravity_accum_ms >= grav_ms:
            self.gravity_accum_ms -= grav_ms
            if self.board.collides(self.active, dy=1):
                break
            self.active.y += 1
            self.active.last_move_was_rotate = False
            if self.soft_dropping:
                self.score += SOFT_DROP_POINTS_PER_CELL

        self._update_on_ground()
        if self.on_ground:
            self.lock_timer_ms += dt_ms
            if self.lock_timer_ms >= LOCK_DELAY_MS:
                self._lock_piece()
        else:
            self.lock_timer_ms = 0.0

    def toggle_pause(self) -> None:
        if self.phase == Phase.PLAYING:
            self.phase = Phase.PAUSED
        elif self.phase == Phase.PAUSED:
            self.phase = Phase.PLAYING

    def restart(self) -> None:
        self.__init__()
