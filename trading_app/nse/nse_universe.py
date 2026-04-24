from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

from nse_config import (
    INDEX_URLS,
    REQUEST_HEADERS,
    REQUEST_TIMEOUT,
    SECTOR_CSV_URLS,
    SECTOR_FALLBACK_SYMBOLS,
    SECTOR_PAGES,
)


class NSEUniverseLoader:
    def __init__(self, *, session: requests.Session | None = None):
        self.session = session or requests.Session()

    @staticmethod
    def _to_fyers(symbols: list[str]) -> list[str]:
        return [f"NSE:{symbol}-EQ" for symbol in symbols]

    @staticmethod
    def _from_fyers(symbols: list[str]) -> list[str]:
        clean: list[str] = []

        for symbol in symbols:
            value = str(symbol).strip()
            if value.startswith("NSE:"):
                value = value[4:]
            if value.endswith("-EQ"):
                value = value[:-3]
            clean.append(value)

        return clean

    def _read_constituent_csv(self, csv_url: str) -> pd.DataFrame:
        try:
            response = self.session.get(
                csv_url,
                headers=REQUEST_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Request failed for CSV URL: {csv_url}") from exc

        try:
            df = pd.read_csv(StringIO(response.text))
        except Exception as exc:
            raise RuntimeError(f"Failed to parse CSV from: {csv_url}") from exc

        if "Symbol" not in df.columns:
            raise RuntimeError(f"'Symbol' column missing in CSV: {csv_url}")

        return df

    @staticmethod
    def get_all_sector_names() -> list[str]:
        try:
            return list(SECTOR_PAGES.keys())
        except Exception:
            return []

    def load_index_constituents(
        self,
        index_name: str,
        *,
        fyers_format: bool = True,
    ) -> list[str]:
        try:
            index_key = str(index_name).strip().upper()
        except Exception:
            return []

        try:
            csv_url = INDEX_URLS[index_key]
        except KeyError:
            return []

        try:
            df = self._read_constituent_csv(csv_url)
            symbols = (
                df["Symbol"]
                .dropna()
                .astype(str)
                .str.strip()
            )
            symbols = [symbol for symbol in symbols if symbol]
            return self._to_fyers(symbols) if fyers_format else symbols
        except Exception:
            return []

    def load_sector_constituents(
        self,
        sector_name: str,
        *,
        fyers_format: bool = True,
    ) -> list[str]:
        try:
            sector_key = str(sector_name).strip().upper()
        except Exception:
            return []

        try:
            fallback_symbols = SECTOR_FALLBACK_SYMBOLS.get(sector_key)
            if fallback_symbols is not None:
                return (
                    list(fallback_symbols)
                    if fyers_format
                    else self._from_fyers(list(fallback_symbols))
                )
        except Exception:
            return []

        try:
            csv_url = SECTOR_CSV_URLS[sector_key]
        except KeyError:
            return []

        try:
            df = self._read_constituent_csv(csv_url)
            symbols = (
                df["Symbol"]
                .dropna()
                .astype(str)
                .str.strip()
            )
            symbols = [symbol for symbol in symbols if symbol]
            return self._to_fyers(symbols) if fyers_format else symbols
        except Exception:
            return []

    def load_all_sectors(self, *, fyers_format: bool = True) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}

        try:
            sector_names = list(SECTOR_PAGES.keys())
        except Exception:
            return result

        for sector_name in sector_names:
            try:
                result[sector_name] = self.load_sector_constituents(
                    sector_name,
                    fyers_format=fyers_format,
                )
            except Exception:
                result[sector_name] = []

        return result

    def load_all_sectors_df(self, *, fyers_format: bool = True) -> pd.DataFrame:
        rows: list[dict[str, str]] = []

        try:
            all_sectors = self.load_all_sectors(fyers_format=fyers_format)
        except Exception:
            return pd.DataFrame(columns=["sector", "symbol"])

        for sector_name, symbols in all_sectors.items():
            try:
                for symbol in symbols:
                    rows.append(
                        {
                            "sector": sector_name,
                            "symbol": symbol,
                        }
                    )
            except Exception:
                continue

        try:
            return pd.DataFrame(rows, columns=["sector", "symbol"])
        except Exception:
            return pd.DataFrame(columns=["sector", "symbol"])
        


loader = NSEUniverseLoader()

nifty200 = loader.load_index_constituents("NIFTY50")
bank_symbols = loader.load_sector_constituents("NIFTY_BANK")
all_sectors = loader.load_all_sectors()
sector_df = loader.load_all_sectors_df()
print(nifty200)