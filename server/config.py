BOARD_HEIGHT = 40
BOARD_MIN_WIDTH = 20
BOARD_MAX_WIDTH = 500
COLUMNS_PER_PLAYER = 2
TICK_RATE = 0.5  # seconds between gravity ticks
SPAWN_TOP_ROW = 0  # row where new pieces appear
LEADERBOARD_SIZE = 10  # top-N players broadcast to everyone
MAX_NAME_LENGTH = 16  # display names are trimmed to this
GROUNDED_TICKS_TO_LOCK = 2  # lock delay: ticks a piece may rest on the ground
IDLE_TICKS_BEFORE_REMOVE = 240  # 240 ticks x 0.5s = 2 min without input -> piece removed
# Per-connection rate limit; excess messages dropped. Must allow legit play:
# DAS auto-repeat is 20 msg/s per held key and 3 keys can repeat at once.
MAX_MESSAGES_PER_SEC = 60
