"""Load test: simulate N concurrent WebSocket players sending random actions.

Usage:
    python -m tests.load_test --players 100 --duration 30 --url ws://localhost:8000/ws

Prints latency stats and throughput when done.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from dataclasses import dataclass, field

import websockets

ACTIONS = ["left", "right", "soft_drop", "rotate_cw", "rotate_ccw", "hard_drop"]


@dataclass
class Stats:
    messages_sent: int = 0
    messages_received: int = 0
    latencies: list[float] = field(default_factory=list)
    errors: int = 0
    connect_time: float = 0.0


async def player(url: str, player_num: int, duration: float, stats: Stats, action_interval: float = 0.2):
    """Simulate a single player: connect, send random actions, measure latency."""
    try:
        t0 = time.monotonic()
        ws = await websockets.connect(url)
        stats.connect_time = max(stats.connect_time, time.monotonic() - t0)

        # Consume welcome + initial state + connect delta
        for _ in range(3):
            try:
                await asyncio.wait_for(ws.recv(), timeout=5.0)
            except Exception:
                break

        end_time = time.monotonic() + duration

        async def reader():
            try:
                async for msg in ws:
                    stats.messages_received += 1
            except Exception:
                pass

        read_task = asyncio.create_task(reader())

        while time.monotonic() < end_time:
            action = random.choice(ACTIONS)
            try:
                await ws.send(json.dumps({"action": action}))
                stats.messages_sent += 1
            except Exception:
                break

            jitter = random.uniform(0.5, 1.5)
            await asyncio.sleep(action_interval * jitter)

        read_task.cancel()
        await ws.close()

    except Exception as e:
        stats.errors += 1
        if player_num < 3:
            print(f"  Player {player_num} error: {e}")


async def run_load_test(url: str, num_players: int, duration: float, ramp_time: float = 5.0):
    print(f"Load test: {num_players} players for {duration}s against {url}")
    print(f"  Ramp-up: {ramp_time}s (staggered connects)")
    print()

    stats = Stats()
    tasks = []

    t_start = time.monotonic()

    # Stagger connections over ramp_time
    delay_per_player = ramp_time / max(num_players, 1)

    async def delayed_player(i: int):
        await asyncio.sleep(i * delay_per_player)
        await player(url, i, duration, stats)

    tasks = [asyncio.create_task(delayed_player(i)) for i in range(num_players)]

    await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.monotonic() - t_start

    print(f"Results ({elapsed:.1f}s total):")
    print(f"  Players:          {num_players}")
    print(f"  Messages sent:    {stats.messages_sent}")
    print(f"  Messages received:{stats.messages_received}")
    print(f"  Send throughput:  {stats.messages_sent / elapsed:.0f} msg/s")
    print(f"  Recv throughput:  {stats.messages_received / elapsed:.0f} msg/s")
    print(f"  Max connect time: {stats.connect_time * 1000:.0f}ms")
    print(f"  Errors:           {stats.errors}")

    if stats.errors > num_players * 0.1:
        print(f"\n  WARNING: {stats.errors}/{num_players} players had errors")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Tetris 1000 load test")
    parser.add_argument("--players", type=int, default=100, help="Number of concurrent players")
    parser.add_argument("--duration", type=float, default=30, help="Test duration in seconds")
    parser.add_argument("--url", default="ws://localhost:8000/ws", help="WebSocket URL")
    parser.add_argument("--ramp", type=float, default=5.0, help="Ramp-up time in seconds")
    args = parser.parse_args()

    asyncio.run(run_load_test(args.url, args.players, args.duration, args.ramp))


if __name__ == "__main__":
    main()
