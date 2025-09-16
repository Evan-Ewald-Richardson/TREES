"""
Application Settings
Environment variable configuration and validation.
"""

import os
from dotenv import load_dotenv

load_dotenv(override=False)


def _require_env(name: str) -> str:
	"""Get required environment variable or raise error."""
	v = os.getenv(name)
	if not v:
		raise RuntimeError(f"Missing required environment variable: {name}")
	return v


# Strava OAuth Configuration
_STRAVA_CLIENT_ID_RAW = _require_env("STRAVA_CLIENT_ID")
try:
	STRAVA_CLIENT_ID = int(_STRAVA_CLIENT_ID_RAW)
except ValueError:
	raise RuntimeError("STRAVA_CLIENT_ID must be an integer")

STRAVA_CLIENT_SECRET = _require_env("STRAVA_CLIENT_SECRET")
STRAVA_REDIRECT_URI = _require_env("STRAVA_REDIRECT_URI")

# Admin Authentication
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "changeme")

# Application Security
SECRET_KEY = _require_env("SECRET_KEY")
FRONTEND_ORIGIN = _require_env("FRONTEND_ORIGIN")