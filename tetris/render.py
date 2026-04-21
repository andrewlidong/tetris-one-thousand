"""Pygame rendering: playfield, active piece, ghost, HUD, overlays."""

from __future__ import annotations

import pygame

from .constants import (
    BG,
    BUFFER_ROWS,
    CELL,
    COLS,
    GHOST_ALPHA,
    GRID,
    HUD_BG,
    HUD_WIDTH,
    PIECE_COLORS,
    TEXT,
    TEXT_DIM,
    VISIBLE_ROWS,
    WINDOW_H,
    WINDOW_W,
)
from .game import GameState, Phase, TSpinKind
from .pieces import SHAPES

PLAYFIELD_X = 0
PLAYFIELD_Y = 0
PLAYFIELD_W = COLS * CELL
PLAYFIELD_H = VISIBLE_ROWS * CELL


def _draw_cell(
    surface: pygame.Surface, col: int, row: int, color, alpha: int | None = None
) -> None:
    """Draw one cell at (col, row) in playfield coordinates (row 0 = top visible row)."""
    if row < 0 or row >= VISIBLE_ROWS:
        return
    x = PLAYFIELD_X + col * CELL
    y = PLAYFIELD_Y + row * CELL
    rect = pygame.Rect(x, y, CELL, CELL)
    if alpha is None:
        pygame.draw.rect(surface, color, rect)
    else:
        s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
        s.fill((*color, alpha))
        surface.blit(s, rect)
    # 1px inset highlight for readability
    pygame.draw.rect(surface, (255, 255, 255, 255), rect, 1)


def _draw_playfield(surface: pygame.Surface, game: GameState) -> None:
    pygame.draw.rect(surface, BG, (PLAYFIELD_X, PLAYFIELD_Y, PLAYFIELD_W, PLAYFIELD_H))
    # Grid lines
    for c in range(COLS + 1):
        x = PLAYFIELD_X + c * CELL
        pygame.draw.line(surface, GRID, (x, 0), (x, PLAYFIELD_H))
    for r in range(VISIBLE_ROWS + 1):
        y = PLAYFIELD_Y + r * CELL
        pygame.draw.line(surface, GRID, (0, y), (PLAYFIELD_W, y))

    # Locked blocks
    for abs_row in range(BUFFER_ROWS, BUFFER_ROWS + VISIBLE_ROWS):
        for col in range(COLS):
            kind = game.board.grid[abs_row][col]
            if kind is not None:
                _draw_cell(surface, col, abs_row - BUFFER_ROWS, PIECE_COLORS[kind])

    # Ghost piece
    if game.active is not None and game.phase == Phase.PLAYING:
        dy = game.ghost_offset()
        if dy > 0:
            color = PIECE_COLORS[game.active.kind]
            for c, r in game.active.cells(y=game.active.y + dy):
                _draw_cell(surface, c, r - BUFFER_ROWS, color, alpha=GHOST_ALPHA)

    # Active piece
    if game.active is not None:
        color = PIECE_COLORS[game.active.kind]
        for c, r in game.active.cells():
            _draw_cell(surface, c, r - BUFFER_ROWS, color)

    # Line-clear flash
    if game.flash_timer_ms > 0 and game.flash_rows:
        flash = pygame.Surface((PLAYFIELD_W, CELL), pygame.SRCALPHA)
        alpha = int(180 * (game.flash_timer_ms / 120.0))
        flash.fill((255, 255, 255, alpha))
        for abs_row in game.flash_rows:
            rr = abs_row - BUFFER_ROWS
            if 0 <= rr < VISIBLE_ROWS:
                surface.blit(flash, (PLAYFIELD_X, PLAYFIELD_Y + rr * CELL))


def _draw_mini_piece(
    surface: pygame.Surface, kind: str, box_x: int, box_y: int, box_w: int, box_h: int
) -> None:
    """Draw a piece centered inside (box_x, box_y, box_w, box_h)."""
    cells = SHAPES[kind][0]
    xs = [c for c, _ in cells]
    ys = [r for _, r in cells]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    piece_w = (max_x - min_x + 1) * (CELL // 2)
    piece_h = (max_y - min_y + 1) * (CELL // 2)
    origin_x = box_x + (box_w - piece_w) // 2 - min_x * (CELL // 2)
    origin_y = box_y + (box_h - piece_h) // 2 - min_y * (CELL // 2)
    color = PIECE_COLORS[kind]
    for c, r in cells:
        rect = pygame.Rect(
            origin_x + c * (CELL // 2), origin_y + r * (CELL // 2), CELL // 2, CELL // 2
        )
        pygame.draw.rect(surface, color, rect)
        pygame.draw.rect(surface, (255, 255, 255), rect, 1)


def _draw_hud(
    surface: pygame.Surface, game: GameState, font: pygame.font.Font, small: pygame.font.Font
) -> None:
    pygame.draw.rect(surface, HUD_BG, (PLAYFIELD_W, 0, HUD_WIDTH, WINDOW_H))
    x0 = PLAYFIELD_W + 16
    y = 16

    def line(text: str, f: pygame.font.Font = font, color=TEXT) -> None:
        nonlocal y
        surface.blit(f.render(text, True, color), (x0, y))
        y += f.get_linesize() + 4

    line("HOLD", small, TEXT_DIM)
    hold_box = pygame.Rect(x0, y, HUD_WIDTH - 32, CELL * 2 + 8)
    pygame.draw.rect(surface, BG, hold_box, border_radius=4)
    pygame.draw.rect(surface, GRID, hold_box, 1, border_radius=4)
    if game.hold is not None:
        _draw_mini_piece(
            surface, game.hold, hold_box.x + 4, hold_box.y + 4, hold_box.w - 8, hold_box.h - 8
        )
    y = hold_box.bottom + 12

    line("NEXT", small, TEXT_DIM)
    for kind in game.bag.preview(5):
        box = pygame.Rect(x0, y, HUD_WIDTH - 32, CELL + 4)
        pygame.draw.rect(surface, BG, box, border_radius=4)
        _draw_mini_piece(surface, kind, box.x + 4, box.y + 2, box.w - 8, box.h - 4)
        y = box.bottom + 4
    y += 6

    line(f"SCORE  {game.score}")
    line(f"LEVEL  {game.level}")
    line(f"LINES  {game.lines}")
    if game.combo > 0:
        line(f"COMBO  {game.combo}", small, TEXT_DIM)
    if game.back_to_back:
        line("B2B", small, TEXT_DIM)

    # Last clear label
    lc = game.last_clear
    label = ""
    if lc.tspin == TSpinKind.FULL:
        label = f"T-SPIN {['', 'SINGLE', 'DOUBLE', 'TRIPLE'][lc.lines] if lc.lines else ''}".strip()
    elif lc.tspin == TSpinKind.MINI:
        label = "T-SPIN MINI"
    elif lc.lines == 4:
        label = "TETRIS"
    if label:
        line(label, small, (255, 200, 80))


def _draw_overlay(surface: pygame.Surface, text: str, font: pygame.font.Font) -> None:
    dim = pygame.Surface((PLAYFIELD_W, PLAYFIELD_H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 160))
    surface.blit(dim, (PLAYFIELD_X, PLAYFIELD_Y))
    rendered = font.render(text, True, TEXT)
    rect = rendered.get_rect(center=(PLAYFIELD_W // 2, PLAYFIELD_H // 2 - 20))
    surface.blit(rendered, rect)


def make_fonts() -> tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font]:
    big = pygame.font.SysFont("menlo,consolas,monospace", 28, bold=True)
    medium = pygame.font.SysFont("menlo,consolas,monospace", 18, bold=True)
    small = pygame.font.SysFont("menlo,consolas,monospace", 14)
    return big, medium, small


def render(
    surface: pygame.Surface,
    game: GameState,
    fonts: tuple[pygame.font.Font, pygame.font.Font, pygame.font.Font],
) -> None:
    big, medium, small = fonts
    surface.fill(BG)
    _draw_playfield(surface, game)
    _draw_hud(surface, game, medium, small)
    if game.phase == Phase.PAUSED:
        _draw_overlay(surface, "PAUSED", big)
        hint = small.render("P/Esc to resume", True, TEXT_DIM)
        surface.blit(hint, hint.get_rect(center=(PLAYFIELD_W // 2, PLAYFIELD_H // 2 + 16)))
    elif game.phase == Phase.GAME_OVER:
        _draw_overlay(surface, "GAME OVER", big)
        hint = small.render("R to restart, Esc to quit", True, TEXT_DIM)
        surface.blit(hint, hint.get_rect(center=(PLAYFIELD_W // 2, PLAYFIELD_H // 2 + 16)))


def window_size() -> tuple[int, int]:
    return (WINDOW_W, WINDOW_H)
