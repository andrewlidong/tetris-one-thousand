"""Keyboard handling with DAS/ARR for horizontal movement."""

from __future__ import annotations

import pygame

from .constants import ARR_MS, DAS_MS
from .game import GameState, Phase


class InputHandler:
    def __init__(self) -> None:
        self.left_held = False
        self.right_held = False
        self.das_timer_ms = 0.0
        self.arr_timer_ms = 0.0
        self.das_direction = 0  # -1 left, +1 right, 0 none

    def handle_event(self, event: pygame.event.Event, game: GameState) -> bool:
        """Returns False if the game should quit."""
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            return self._on_keydown(event, game)
        if event.type == pygame.KEYUP:
            self._on_keyup(event, game)
        return True

    def _on_keydown(self, event: pygame.event.Event, game: GameState) -> bool:
        key = event.key
        if key == pygame.K_ESCAPE:
            if game.phase == Phase.GAME_OVER:
                return False
            game.toggle_pause()
            return True
        if key == pygame.K_p:
            game.toggle_pause()
            return True
        if key == pygame.K_r:
            game.restart()
            return True

        if game.phase != Phase.PLAYING:
            return True

        if key == pygame.K_LEFT:
            self.left_held = True
            self.das_direction = -1
            self.das_timer_ms = 0.0
            self.arr_timer_ms = 0.0
            game.try_move(-1, 0)
        elif key == pygame.K_RIGHT:
            self.right_held = True
            self.das_direction = 1
            self.das_timer_ms = 0.0
            self.arr_timer_ms = 0.0
            game.try_move(1, 0)
        elif key == pygame.K_DOWN:
            game.soft_dropping = True
        elif key == pygame.K_SPACE:
            game.hard_drop()
        elif key in (pygame.K_UP, pygame.K_x):
            game.try_rotate(1)
        elif key in (pygame.K_z, pygame.K_LCTRL, pygame.K_RCTRL):
            game.try_rotate(-1)
        elif key in (pygame.K_c, pygame.K_LSHIFT, pygame.K_RSHIFT):
            game.hold_piece()
        return True

    def _on_keyup(self, event: pygame.event.Event, game: GameState) -> None:
        key = event.key
        if key == pygame.K_LEFT:
            self.left_held = False
            if self.das_direction == -1:
                self.das_direction = 1 if self.right_held else 0
                self.das_timer_ms = 0.0
                self.arr_timer_ms = 0.0
        elif key == pygame.K_RIGHT:
            self.right_held = False
            if self.das_direction == 1:
                self.das_direction = -1 if self.left_held else 0
                self.das_timer_ms = 0.0
                self.arr_timer_ms = 0.0
        elif key == pygame.K_DOWN:
            game.soft_dropping = False

    def update(self, dt_ms: float, game: GameState) -> None:
        if game.phase != Phase.PLAYING or self.das_direction == 0:
            return
        self.das_timer_ms += dt_ms
        if self.das_timer_ms < DAS_MS:
            return
        self.arr_timer_ms += dt_ms
        while self.arr_timer_ms >= ARR_MS:
            self.arr_timer_ms -= ARR_MS
            if not game.try_move(self.das_direction, 0):
                break
