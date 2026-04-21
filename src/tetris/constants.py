"""Game constants: dimensions, colors, timings, scoring, gravity."""

from __future__ import annotations

CELL = 30
COLS = 10
VISIBLE_ROWS = 20
BUFFER_ROWS = 20
TOTAL_ROWS = VISIBLE_ROWS + BUFFER_ROWS

HUD_WIDTH = 220
WINDOW_W = COLS * CELL + HUD_WIDTH
WINDOW_H = VISIBLE_ROWS * CELL
FPS = 60

# Colors
BG = (18, 18, 24)
GRID = (40, 40, 52)
HUD_BG = (26, 26, 34)
TEXT = (230, 230, 240)
TEXT_DIM = (140, 140, 160)
GHOST_ALPHA = 90

PIECE_COLORS: dict[str, tuple[int, int, int]] = {
    "I": (0, 240, 240),
    "O": (240, 240, 0),
    "T": (160, 0, 240),
    "S": (0, 240, 0),
    "Z": (240, 0, 0),
    "J": (0, 0, 240),
    "L": (240, 160, 0),
}

# Timings (milliseconds)
DAS_MS = 170
ARR_MS = 50
SOFT_DROP_MULT = 20  # gravity multiplier while soft-dropping
LOCK_DELAY_MS = 500
LOCK_RESET_CAP = 15  # max number of move/rotate lock resets

# Gravity: frames per cell at each level, indexed by level (1..20+).
# Tetris guideline Hz at 60 FPS.
GRAVITY_FRAMES = [
    48,  # L1
    43,
    38,
    33,
    28,
    23,
    18,
    13,
    8,
    6,
    5,
    5,
    5,
    4,
    4,
    4,
    3,
    3,
    3,
    2,  # L20+
]


def gravity_ms_for_level(level: int) -> float:
    """Return ms-per-cell for the given level (1-indexed)."""
    idx = max(0, min(len(GRAVITY_FRAMES) - 1, level - 1))
    frames = GRAVITY_FRAMES[idx]
    return frames * (1000.0 / 60.0)


# Scoring (guideline)
SCORE_SINGLE = 100
SCORE_DOUBLE = 300
SCORE_TRIPLE = 500
SCORE_TETRIS = 800
SCORE_TSPIN_MINI = 100
SCORE_TSPIN_MINI_SINGLE = 200
SCORE_TSPIN = 400
SCORE_TSPIN_SINGLE = 800
SCORE_TSPIN_DOUBLE = 1200
SCORE_TSPIN_TRIPLE = 1600
B2B_MULT = 1.5
COMBO_BONUS = 50  # per combo count
SOFT_DROP_POINTS_PER_CELL = 1
HARD_DROP_POINTS_PER_CELL = 2

LINES_PER_LEVEL = 10
