"""Async main loop. Structure is pygbag-compatible: await asyncio.sleep(0) per frame."""

from __future__ import annotations

import asyncio

import pygame

from .constants import FPS
from .game import GameState
from .input import InputHandler
from .render import make_fonts, render, window_size


async def run() -> None:
    print("[tetris] run() start")
    pygame.init()
    pygame.display.set_caption("Tetris")
    print(f"[tetris] set_mode {window_size()}")
    screen = pygame.display.set_mode(window_size())
    clock = pygame.time.Clock()
    fonts = make_fonts()
    print("[tetris] init complete, entering loop")

    game = GameState()
    inputs = InputHandler()
    running = True

    while running:
        dt = clock.tick(FPS)
        for event in pygame.event.get():
            if not inputs.handle_event(event, game):
                running = False
                break
        inputs.update(dt, game)
        game.update(dt)
        render(screen, game, fonts)
        pygame.display.flip()
        await asyncio.sleep(0)

    pygame.quit()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
