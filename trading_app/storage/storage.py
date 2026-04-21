import json
from pathlib import Path
import pandas as pd


BASE_DIR = Path("data")
SPOT_DIR = BASE_DIR / "spot"
OPTION_DIR = BASE_DIR / "options"
STATE_FILE = BASE_DIR / "state" / "history_state.json"


def _ensure_dirs() -> None:
    SPOT_DIR.mkdir(parents=True, exist_ok=True)
    OPTION_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _symbol_to_filename(symbol: str) -> str:
    return symbol.replace(":", "_")


# ---------------- STATE ---------------- #

def load_state() -> dict:
    _ensure_dirs()

    if not STATE_FILE.exists():
        return {}

    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    _ensure_dirs()

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------------- DATA ---------------- #

def get_symbol_file(symbol: str, is_spot: bool) -> Path:
    filename = _symbol_to_filename(symbol) + ".parquet"

    if is_spot:
        return SPOT_DIR / filename
    return OPTION_DIR / filename


def load_symbol_data(symbol: str, is_spot: bool) -> pd.DataFrame:
    path = get_symbol_file(symbol, is_spot)

    if not path.exists():
        return pd.DataFrame()

    return pd.read_parquet(path)


def save_symbol_data(symbol: str, df: pd.DataFrame, is_spot: bool) -> None:
    path = get_symbol_file(symbol, is_spot)

    if df.empty:
        return

    df.to_parquet(path, index=False)


def append_symbol_data(symbol: str, new_df: pd.DataFrame, is_spot: bool) -> pd.DataFrame:
    old_df = load_symbol_data(symbol, is_spot)

    if old_df.empty:
        combined = new_df
    else:
        combined = pd.concat([old_df, new_df], ignore_index=True)

        # duplicate remove based on timestamp
        combined = combined.drop_duplicates(subset=["timestamp"], keep="last")

        combined = combined.sort_values("timestamp")

    save_symbol_data(symbol, combined, is_spot)

    return combined