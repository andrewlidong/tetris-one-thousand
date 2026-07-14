BOARD_HEIGHT = 40
BOARD_MIN_WIDTH = 20
BOARD_MAX_WIDTH = 500
COLUMNS_PER_PLAYER = 2
TICK_RATE = 0.5  # base seconds between gravity ticks (speed level 0)
MIN_TICK_RATE = 0.15  # gravity never gets faster than this
LINES_PER_SPEEDUP = 10  # team lines cleared (per round) per speed level
SPEEDUP_PER_LEVEL = 0.05  # seconds shaved off the tick interval per level
SPAWN_TOP_ROW = 0  # row where new pieces appear
LEADERBOARD_SIZE = 10  # top-N players broadcast to everyone
MAX_NAME_LENGTH = 16  # display names are trimmed to this
GROUNDED_TICKS_TO_LOCK = 2  # lock delay: ticks a piece may rest on the ground
IDLE_TICKS_BEFORE_REMOVE = 240  # 240 ticks x 0.5s = 2 min without input -> piece removed
# Per-connection rate limit; excess messages dropped. Must allow legit play:
# DAS auto-repeat is 20 msg/s per held key and 3 keys can repeat at once.
MAX_MESSAGES_PER_SEC = 60
BROADCAST_CHUNK = 50  # concurrent sends per asyncio.gather batch
DORMANT_LIMIT = 500  # disconnected identities remembered for reconnect
BIG_CLEAR_MIN = 3  # clearing this many lines at once is announced to everyone
FRENZY_INTERVAL_TICKS = 360  # ticks between frenzies (~3 min at base speed)
FRENZY_DURATION_TICKS = 60  # frenzy length in ticks (~30s at base speed)
FRENZY_MULTIPLIER = 2  # score multiplier while a frenzy is active
