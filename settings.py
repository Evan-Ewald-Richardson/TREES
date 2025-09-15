import os
from dotenv import load_dotenv

# Load .env once, early
load_dotenv(override=False)

def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v

# Strava
_STRAVA_CLIENT_ID_RAW = _require_env("STRAVA_CLIENT_ID")
try:
    STRAVA_CLIENT_ID = int(_STRAVA_CLIENT_ID_RAW)
except ValueError:
    raise RuntimeError("STRAVA_CLIENT_ID must be an integer")

STRAVA_CLIENT_SECRET = _require_env("STRAVA_CLIENT_SECRET")
STRAVA_REDIRECT_URI  = _require_env("STRAVA_REDIRECT_URI")

# Admin basic auth
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "changeme")

# App secret (for state tokens, etc)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-please-change")