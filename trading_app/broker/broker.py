from __future__ import annotations

from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo
import time as tt

import pandas as pd
from fyers_apiv3 import fyersModel

from .auth import login
from ..settings import validate_settings


MARKET_TZ = ZoneInfo("Asia/Kolkata")
MARKET_OPEN_TIME = time(9, 15)


def epoch_to_ist(epoch: int) -> str:
    """Convert epoch seconds to IST datetime string."""
    return datetime.fromtimestamp(epoch, MARKET_TZ).strftime("%Y-%m-%d %H:%M:%S")


class Broker:
    """FYERS broker wrapper.

    Responsibilities:
    - authentication
    - profile/orders/positions/holdings
    - quotes/depth
    - date based history fetch
    - epoch based history fetch
    - chunked history fetch with throttling
    - completed candle filtering
    """

    def __init__(self, *, auto_login: bool = True) -> None:
        """Initialize broker wrapper."""
        self._auto_login = auto_login
        self._client: fyersModel.FyersModel | None = None

    def get_client(self) -> fyersModel.FyersModel:
        """Return authenticated FYERS client."""
        if self._client is None:
            if not self._auto_login:
                raise RuntimeError(
                    "FYERS client is not authenticated and auto_login is disabled."
                )
            validate_settings()
            self._client = login()
        return self._client

    def refresh_login(self) -> fyersModel.FyersModel:
        """Refresh FYERS login and return fresh client."""
        validate_settings()
        self._client = login()
        return self._client

    def get_profile(self) -> dict[str, Any]:
        """Fetch profile response."""
        response = self.get_client().get_profile()
        if not isinstance(response, dict):
            raise RuntimeError("Invalid profile response from FYERS.")
        return response

    def get_history(
        self,
        symbol: str,
        resolution: str,
        date_from: date,
        date_to: date,
        *,
        cont_flag: str = "1",
        date_format: str = "1",
        include_live_candle: bool = False,
    ) -> pd.DataFrame:
        """Fetch history using yyyy-mm-dd date range and return DataFrame."""
        payload = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": date_format,
            "range_from": date_from.strftime("%Y-%m-%d"),
            "range_to": date_to.strftime("%Y-%m-%d"),
            "cont_flag": cont_flag,
        }

        response = self.get_client().history(data=payload)

        if not isinstance(response, dict):
            return pd.DataFrame(columns=self._history_columns())

        candles = response.get("candles", [])
        if not isinstance(candles, list):
            return pd.DataFrame(columns=self._history_columns())

        return self._candles_to_df(
            symbol=symbol,
            candles=candles,
            resolution=resolution,
            include_live_candle=include_live_candle,
        )

    def get_history_epoch(
        self,
        *,
        symbol: str,
        resolution: str,
        range_from_epoch: int,
        range_to_epoch: int,
        cont_flag: str = "1",
        include_live_candle: bool = False,
    ) -> pd.DataFrame:
        """Fetch history using exact epoch range and return DataFrame."""
        payload = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": "0",
            "range_from": str(range_from_epoch),
            "range_to": str(range_to_epoch),
            "cont_flag": cont_flag,
        }

        response = self.get_client().history(data=payload)

        if not isinstance(response, dict):
            return pd.DataFrame(columns=self._history_columns())

        candles = response.get("candles", [])
        if not isinstance(candles, list):
            return pd.DataFrame(columns=self._history_columns())

        return self._candles_to_df(
            symbol=symbol,
            candles=candles,
            resolution=resolution,
            include_live_candle=include_live_candle,
        )

    def get_history_chunked_epoch(
        self,
        *,
        symbol: str,
        resolution: str,
        range_from_epoch: int,
        range_to_epoch: int,
        cont_flag: str = "1",
        include_live_candle: bool = False,
        request_delay: float = 0.34,
    ) -> pd.DataFrame:
        """Fetch large epoch range using API-safe chunks and return merged DataFrame."""
        chunks = self._build_history_epoch_chunks(
            range_from_epoch=range_from_epoch,
            range_to_epoch=range_to_epoch,
            resolution=resolution,
        )

        frames: list[pd.DataFrame] = []

        for i, (chunk_from, chunk_to) in enumerate(chunks):
            if i > 0 and request_delay > 0:
                tt.sleep(request_delay)

            df = self.get_history_epoch(
                symbol=symbol,
                resolution=resolution,
                range_from_epoch=chunk_from,
                range_to_epoch=chunk_to,
                cont_flag=cont_flag,
                include_live_candle=include_live_candle,
            )

            if not df.empty:
                frames.append(df)

        if not frames:
            return pd.DataFrame(columns=self._history_columns())

        merged = pd.concat(frames, ignore_index=True)
        merged = merged.drop_duplicates(subset=["timestamp"], keep="last")
        merged = merged.sort_values("timestamp").reset_index(drop=True)

        return merged

    def get_history_for_symbols(
        self,
        *,
        symbols: list[str],
        resolution: str,
        date_from,
        date_to,
        cont_flag: str = "1",
        include_live_candle: bool = False,
        request_delay: float = 0.34,
    ) -> dict[str, pd.DataFrame]:
        """Fetch date based history for multiple symbols with throttling."""
        results: dict[str, pd.DataFrame] = {}

        for i, symbol in enumerate(symbols):
            if i > 0 and request_delay > 0:
                tt.sleep(request_delay)

            results[symbol] = self.get_history(
                symbol=symbol,
                resolution=resolution,
                date_from=date_from,
                date_to=date_to,
                cont_flag=cont_flag,
                include_live_candle=include_live_candle,
            )

        return results

    def get_orderbook(self) -> dict[str, Any]:
        """Fetch orderbook."""
        response = self.get_client().orderbook()
        if not isinstance(response, dict):
            raise RuntimeError("Invalid orderbook response from FYERS.")
        return response

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel order by order id."""
        payload = {"id": order_id}
        response = self.get_client().cancel_order(payload)
        if not isinstance(response, dict):
            raise RuntimeError("Invalid cancel_order response from FYERS.")
        return response

    def get_positions(self) -> dict[str, Any]:
        """Fetch positions."""
        response = self.get_client().positions()
        if not isinstance(response, dict):
            raise RuntimeError("Invalid positions response from FYERS.")
        return response

    def get_holdings(self) -> dict[str, Any]:
        """Fetch holdings."""
        response = self.get_client().holdings()
        if not isinstance(response, dict):
            raise RuntimeError("Invalid holdings response from FYERS.")
        return response

    def place_order(
        self,
        *,
        symbol: str,
        qty: int,
        side: int,
        productType: str = "INTRADAY",
        orderType: int = 2,
        limitPrice: float = 0,
        stopPrice: float = 0,
        validity: str = "DAY",
        disclosedQty: int = 0,
        offlineOrder: bool = False,
        stopLoss: float = 0,
        takeProfit: float = 0,
    ) -> dict[str, Any]:
        """Place order using FYERS order API."""
        payload = {
            "symbol": symbol,
            "qty": qty,
            "type": orderType,
            "side": side,
            "productType": productType,
            "limitPrice": limitPrice,
            "stopPrice": stopPrice,
            "validity": validity,
            "disclosedQty": disclosedQty,
            "offlineOrder": offlineOrder,
            "stopLoss": stopLoss,
            "takeProfit": takeProfit,
        }

        response = self.get_client().place_order(payload)
        if not isinstance(response, dict):
            raise RuntimeError("Invalid place_order response from FYERS.")

        return response

    def get_quotes(self, *, symbols: list[str]) -> dict[str, Any]:
        """Fetch quotes for multiple symbols."""
        client = self.get_client()

        data = {
            "symbols": ",".join(symbols),
        }

        return client.quotes(data=data)

    def get_depth(self, *, symbols: list[str], ohlcv_flag: int = 1) -> dict[str, Any]:
        """Fetch depth for symbol list."""
        client = self.get_client()

        data = {
            "symbol": ",".join(symbols),
            "ohlcv_flag": str(ohlcv_flag),
        }

        return client.depth(data=data)

    def get_index_spot_prices(self) -> dict[str, dict[str, float]]:
        """Return spot open and current price for NIFTY and SENSEX."""
        symbols = [
            "NSE:NIFTY50-INDEX",
            "BSE:SENSEX-INDEX",
        ]

        response = self.get_quotes(symbols=symbols)
        result: dict[str, dict[str, float]] = {}

        data = response.get("d", [])
        if not isinstance(data, list):
            return result

        for item in data:
            symbol = str(item.get("n", ""))
            values = item.get("v", {})

            open_price = float(values.get("open_price", 0))
            current_price = float(values.get("lp", 0))

            if symbol == "NSE:NIFTY50-INDEX":
                key = "NIFTY"
            elif symbol == "BSE:SENSEX-INDEX":
                key = "SENSEX"
            else:
                continue

            result[key] = {
                "open": open_price,
                "current": current_price,
            }

        return result

    def _history_columns(self) -> list[str]:
        """Return standard history DataFrame columns."""
        return [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "symbol",
        ]

    def _candles_to_df(
        self,
        *,
        symbol: str,
        candles: list[list[Any]],
        resolution: str,
        include_live_candle: bool,
    ) -> pd.DataFrame:
        """Convert raw FYERS candle list to standardized DataFrame."""
        if not candles:
            return pd.DataFrame(columns=self._history_columns())

        df = pd.DataFrame(
            candles,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ],
        )

        df["timestamp"] = df["timestamp"].astype(int)
        df["symbol"] = symbol

        df = self._filter_history_candles_df(
            df=df,
            timeframe_seconds=self._get_resolution_seconds(resolution=resolution),
            include_live_candle=include_live_candle,
        )

        if df.empty:
            return pd.DataFrame(columns=self._history_columns())

        df = df.sort_values("timestamp").reset_index(drop=True)

        return df

    def _get_now_epoch(self) -> int:
        """Return current epoch in IST."""
        return int(datetime.now(MARKET_TZ).timestamp())

    def _get_resolution_seconds(self, *, resolution: str) -> int:
        """Return candle size in seconds for given resolution."""
        normalized_resolution = str(resolution).strip().upper()

        second_map = {
            "5S": 5,
            "10S": 10,
            "15S": 15,
            "30S": 30,
            "45S": 45,
        }

        minute_map = {
            "1": 60,
            "2": 120,
            "3": 180,
            "5": 300,
            "10": 600,
            "15": 900,
            "20": 1200,
            "30": 1800,
            "45": 2700,
            "60": 3600,
            "120": 7200,
            "180": 10800,
            "240": 14400,
        }

        higher_map = {
            "D": 86400,
            "1D": 86400,
            "1W": 7 * 86400,
            "1M": 30 * 86400,
        }

        if normalized_resolution in second_map:
            return second_map[normalized_resolution]

        if normalized_resolution in minute_map:
            return minute_map[normalized_resolution]

        if normalized_resolution in higher_map:
            return higher_map[normalized_resolution]

        raise ValueError(f"Unsupported resolution: {resolution}")

    def _filter_history_candles_df(
        self,
        *,
        df: pd.DataFrame,
        timeframe_seconds: int,
        include_live_candle: bool = False,
    ) -> pd.DataFrame:
        """Remove running candle unless include_live_candle is True."""
        if include_live_candle or df.empty:
            return df

        now_epoch = self._get_now_epoch()
        mask = (df["timestamp"] + timeframe_seconds) <= now_epoch

        return df.loc[mask].reset_index(drop=True)

    def _get_history_chunk_seconds(self, *, resolution: str) -> int:
        """Return maximum epoch window per request for a resolution."""
        normalized_resolution = str(resolution).strip().upper()

        if normalized_resolution in {"5S", "10S", "15S", "30S", "45S"}:
            return 30 * 24 * 60 * 60

        if normalized_resolution in {
            "1",
            "2",
            "3",
            "5",
            "10",
            "15",
            "20",
            "30",
            "45",
            "60",
            "120",
            "180",
            "240",
        }:
            return 100 * 24 * 60 * 60

        if normalized_resolution in {"D", "1D", "1W", "1M"}:
            return 366 * 24 * 60 * 60

        raise ValueError(f"Unsupported resolution: {resolution}")

    def _build_history_epoch_chunks(
        self,
        *,
        range_from_epoch: int,
        range_to_epoch: int,
        resolution: str,
    ) -> list[tuple[int, int]]:
        """Split epoch range into API-safe chunks."""
        if range_from_epoch > range_to_epoch:
            return []

        max_chunk_seconds = self._get_history_chunk_seconds(resolution=resolution)
        chunks: list[tuple[int, int]] = []
        current_start = int(range_from_epoch)

        while current_start <= range_to_epoch:
            current_end = min(current_start + max_chunk_seconds - 1, range_to_epoch)
            chunks.append((current_start, current_end))
            current_start = current_end + 1

        return chunks

    def get_market_start_epoch(self, *, days_back: int) -> int:
        """Return epoch for market open 09:15:00 IST on target day."""
        target_date = (datetime.now(MARKET_TZ) - timedelta(days=days_back)).date()
        start_dt = datetime.combine(target_date, MARKET_OPEN_TIME, tzinfo=MARKET_TZ)
        return int(start_dt.timestamp())

    # def get_completed_range_to_epoch(self, *, resolution: str) -> int:
    #     """Return safe range_to epoch for completed candles only."""
    #     now_dt = datetime.now(MARKET_TZ)
    #     resolution_seconds = self._get_resolution_seconds(resolution=resolution)
    #     completed_to_dt = now_dt - timedelta(seconds=resolution_seconds)
    #     return int(completed_to_dt.timestamp())
    def get_completed_range_to_epoch(self,*,resolution: str,) -> int:
        resolution_seconds = self._get_resolution_seconds(resolution=resolution)
        now_dt = datetime.now(MARKET_TZ)

        market_open_dt = datetime.combine(now_dt.date(), time(9, 15), tzinfo=MARKET_TZ)
        market_close_dt = datetime.combine(now_dt.date(), time(15, 30), tzinfo=MARKET_TZ)

        effective_dt = min(now_dt, market_close_dt)

        elapsed_seconds = int((effective_dt - market_open_dt).total_seconds())

        if elapsed_seconds < resolution_seconds:
            return int(market_open_dt.timestamp()) - 1

        completed_bucket_count = elapsed_seconds // resolution_seconds

        completed_bucket_start = market_open_dt + timedelta(
                                                        seconds=(completed_bucket_count - 1) * resolution_seconds
                                                        )

        completed_range_to_dt = completed_bucket_start + timedelta(seconds=resolution_seconds - 1)

        return int(completed_range_to_dt.timestamp())





if __name__ == "__main__":
    broker = Broker()

    symbol = "NSE:NIFTY50-INDEX"
    resolution = "1"
    days_back = 180

    range_from_epoch = broker.get_market_start_epoch(days_back=days_back)
    range_to_epoch = broker.get_completed_range_to_epoch(resolution=resolution)

    chunks = broker._build_history_epoch_chunks(
                                                range_from_epoch=range_from_epoch,
                                                range_to_epoch=range_to_epoch,
                                                resolution=resolution,
                                            )

    print("SYMBOL:", symbol)
    print("RESOLUTION:", resolution)
    print("TOTAL CHUNKS:", len(chunks))
    print("REQUEST FROM:", epoch_to_ist(range_from_epoch), range_from_epoch)
    print("REQUEST TO  :", epoch_to_ist(range_to_epoch), range_to_epoch)

    df = broker.get_history_chunked_epoch(
                                            symbol=symbol,
                                            resolution=resolution,
                                            range_from_epoch=range_from_epoch,
                                            range_to_epoch=range_to_epoch,
                                            cont_flag="1",
                                            include_live_candle=False,
                                            request_delay=0.34,
                                        )

    print("\n=== FINAL SUMMARY ===")
    print("TOTAL MERGED CANDLES:", len(df))

    if not df.empty:
        first = df.iloc[0]
        last = df.iloc[-1]

        print("MERGED FIRST TIME IST:", epoch_to_ist(int(first["timestamp"])), int(first["timestamp"]))
        print("MERGED LAST TIME IST :", epoch_to_ist(int(last["timestamp"])), int(last["timestamp"]))


# python -m trading_app.broker.broker