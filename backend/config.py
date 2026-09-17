# ============================================================
# SIH 2026 — Backend configuration
# ============================================================
# Put your YouTube Data API v3 key here.
# Do NOT put the key in the website GUI.

YOUTUBE_API_KEY = "YOURAPIKEY"

# Safety limits for the prototype. YouTube API quota is consumed by search
# and comment requests, so keep these sensible during demos.
DEFAULT_VIDEOS = 10
DEFAULT_COMMENTS_PER_VIDEO = 100
MAX_VIDEOS = 25
MAX_COMMENTS_PER_VIDEO = 500

# Optional: if True, the API can be exercised without YouTube credentials.
# Keep False for the real SIH pipeline.
DEMO_MODE = False
