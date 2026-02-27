"""
SkyFrame Configuration v2 — with AI Enhancement support
"""

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
DB_PATH = BASE_DIR / "skyframe.db"

# ── Upload limits ──────────────────────────────────────
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
ALLOWED_MIME_TYPES = {"video/mp4", "video/quicktime"}
ALLOWED_EXTENSIONS = {".mp4", ".mov"}

# ── Server ─────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
CORS_ORIGINS = ["*"]

# ── Download link expiry (seconds) ─────────────────────
DOWNLOAD_LINK_TTL = 300

# ── Replicate AI ───────────────────────────────────────
# Set your token: export REPLICATE_API_TOKEN=r8_xxxxx
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")

# Model choices (swap easily)
REPLICATE_MODELS = {
    "upscale": "lucataco/real-esrgan-video",       # General upscale, free-tier friendly
    "upscale_premium": "topazlabs/video-upscale",  # Premium quality, paid
}

# Default enhancement config
DEFAULT_ENHANCE_MODEL = "upscale"
DEFAULT_SCALE_FACTOR = 2  # 2x upscale

# ── Job polling ────────────────────────────────────────
JOB_POLL_INTERVAL_SEC = 5   # How often the worker checks Replicate status
JOB_MAX_WAIT_SEC = 600      # 10 min timeout per job
