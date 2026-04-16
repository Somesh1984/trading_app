

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "https://127.0.0.1:5000/")
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "")
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "")
FYERS_USER_ID = os.getenv("FYERS_USER_ID", "")
FYERS_TOTP_KEY = os.getenv("FYERS_TOTP_KEY", "")
FYERS_PIN = os.getenv("FYERS_PIN", "")


def validate_settings() -> None:
    required = {
        "FYERS_CLIENT_ID": FYERS_CLIENT_ID,
        "FYERS_SECRET_KEY": FYERS_SECRET_KEY,
        "FYERS_USER_ID": FYERS_USER_ID,
        "FYERS_TOTP_KEY": FYERS_TOTP_KEY,
        "FYERS_PIN": FYERS_PIN,
        "FYERS_REDIRECT_URI": FYERS_REDIRECT_URI,
    }

    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing FYERS settings: {', '.join(missing)}")