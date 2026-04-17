from __future__ import annotations

import json
from pathlib import Path

from .api import FyersApiClient
from .models import FyersSymbol


class FyersSymbolService:
    def __init__(self, api: FyersApiClient, cache_path: str = "") -> None:
        self.api = api
        self.cache_path = cache_path

    def fetch_symbol_master(self) -> list[FyersSymbol]:
        raise NotImplementedError("Implement real Fyers symbol master download later")

    def save_cache(self, symbols: list[FyersSymbol]) -> None:
        if not self.cache_path:
            raise ValueError("cache_path is not configured")

        path = Path(self.cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [symbol.__dict__ for symbol in symbols]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_cache(self) -> list[FyersSymbol]:
        if not self.cache_path:
            return []

        path = Path(self.cache_path)
        if not path.exists() or not path.is_file():
            return []

        raw = json.loads(path.read_text(encoding="utf-8"))
        return [FyersSymbol(**item) for item in raw]

    def search(self, query: str) -> list[FyersSymbol]:
        q = query.strip().lower()
        if not q:
            return []

        symbols = self.load_cache()
        return [
            item
            for item in symbols
            if q in item.symbol.lower() or q in item.display_name.lower()
        ]
