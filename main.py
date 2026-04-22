
from __future__ import annotations

import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from trading_app.broker.broker import Broker
from trading_app.broker.candle_manager import CandleManager
from trading_app.broker.candle_runner import CandleRunner
from trading_app.broker.market_stream import MarketStream
from trading_app.models import LiveCandle


SYMBOL = "NSE:NIFTY50-INDEX"
IST = ZoneInfo("Asia/Kolkata")


def epoch_to_ist_text(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, IST).strftime("%Y-%m-%d %H:%M:%S")


def candle_to_row(candle: LiveCandle) -> dict:
    return {
        "symbol": candle.symbol,
        "bucket_epoch": candle.bucket_epoch,
        "ist_time": epoch_to_ist_text(candle.bucket_epoch),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
    }




def append_rows_to_csv(filename: str, rows: list[dict]) -> None:
    if not rows:
        return

    df = pd.DataFrame(rows)
    file_exists = os.path.exists(filename)

    df.to_csv(
        filename,
        mode="a",
        header=not file_exists,
        index=False,
    )


def append_candle_to_csv(filename: str, candle: LiveCandle) -> None:
    append_rows_to_csv(filename, [candle_to_row(candle)])


def read_existing_csv(filename: str, symbol: str) -> pd.DataFrame:
    if not os.path.exists(filename):
        return pd.DataFrame()

    df = pd.read_csv(filename)
    if df.empty:
        return df

    if "symbol" in df.columns:
        df = df[df["symbol"] == symbol].copy()

    if "bucket_epoch" in df.columns:
        subset_cols = ["bucket_epoch"]
        if "symbol" in df.columns:
            subset_cols = ["symbol", "bucket_epoch"]

        df = (
            df.sort_values("bucket_epoch")
            .drop_duplicates(subset=subset_cols, keep="last")
            .reset_index(drop=True)
        )

    return df


def get_last_csv_bucket(filename: str, symbol: str) -> int | None:
    df = read_existing_csv(filename, symbol)
    if df.empty:
        return None
    return int(df.iloc[-1]["bucket_epoch"])


def build_live_candles_from_csv(
    df: pd.DataFrame,
    *,
    symbol: str,
    timeframe_seconds: int,
) -> list[LiveCandle]:
    candles: list[LiveCandle] = []

    if df.empty:
        return candles

    for row in df.itertuples(index=False):
        candles.append(
            LiveCandle(
                symbol=symbol,
                bucket_epoch=int(row.bucket_epoch),
                timeframe_seconds=timeframe_seconds,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=0,
                is_complete=True,
            )
        )

    return candles


def fetch_history_range(
    *,
    broker: Broker,
    symbol: str,
    resolution: str,
    range_from_epoch: int,
    range_to_epoch: int,
) -> pd.DataFrame:
    if range_from_epoch > range_to_epoch:
        return pd.DataFrame()

    return broker.get_history_chunked_epoch(
        symbol=symbol,
        resolution=resolution,
        range_from_epoch=range_from_epoch,
        range_to_epoch=range_to_epoch,
        cont_flag="1",
        include_live_candle=False,
        request_delay=0.34,
    )


def sync_csv_from_history(
    *,
    broker: Broker,
    symbol: str,
    resolution: str,
    timeframe_seconds: int,
    csv_file: str,
    default_lookback_seconds: int,
) -> pd.DataFrame:
    existing_df = read_existing_csv(csv_file, symbol)
    last_csv_bucket = None if existing_df.empty else int(existing_df.iloc[-1]["bucket_epoch"])

    range_to_epoch = broker.get_completed_range_to_epoch(resolution=resolution)

    if last_csv_bucket is None:
        range_from_epoch = max(0, range_to_epoch - default_lookback_seconds + 1)
    else:
        range_from_epoch = last_csv_bucket + timeframe_seconds

    hist_df = fetch_history_range(
        broker=broker,
        symbol=symbol,
        resolution=resolution,
        range_from_epoch=range_from_epoch,
        range_to_epoch=range_to_epoch,
    )

    if not hist_df.empty:
        rows: list[dict] = []

        for row in hist_df.itertuples(index=False):
            bucket_epoch = int(row.timestamp)
            rows.append(
                {
                    "symbol": symbol,
                    "bucket_epoch": bucket_epoch,
                    "ist_time": epoch_to_ist_text(bucket_epoch),
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                }
            )

        append_rows_to_csv(csv_file, rows)

    updated_df = read_existing_csv(csv_file, symbol)

    print(
        f"CSV SYNC {resolution}: existing_last={last_csv_bucket} fetched={len(hist_df)} final_count={len(updated_df)}",
        flush=True,
    )

    if not updated_df.empty:
        first_bucket = int(updated_df.iloc[0]["bucket_epoch"])
        last_bucket = int(updated_df.iloc[-1]["bucket_epoch"])
        print(
            f"CSV SYNC {resolution} RANGE: {epoch_to_ist_text(first_bucket)} -> {epoch_to_ist_text(last_bucket)}",
            flush=True,
        )

    return updated_df


def seed_manager_from_csv(
    *,
    manager: CandleManager,
    csv_df: pd.DataFrame,
    symbol: str,
    timeframe_seconds: int,
) -> int:
    candles = build_live_candles_from_csv(
        csv_df,
        symbol=symbol,
        timeframe_seconds=timeframe_seconds,
    )
    return manager.seed_closed_candles(candles)


def backfill_gap_to_csv(
    *,
    broker: Broker,
    symbol: str,
    resolution: str,
    timeframe_seconds: int,
    csv_file: str,
    last_bucket: int,
    next_live_bucket: int,
) -> pd.DataFrame:
    missing_from = last_bucket + timeframe_seconds
    missing_to = next_live_bucket - timeframe_seconds

    if missing_from > missing_to:
        return pd.DataFrame()

    gap_df = fetch_history_range(
        broker=broker,
        symbol=symbol,
        resolution=resolution,
        range_from_epoch=missing_from,
        range_to_epoch=missing_to,
    )

    if not gap_df.empty:
        rows: list[dict] = []

        for row in gap_df.itertuples(index=False):
            bucket_epoch = int(row.timestamp)
            rows.append(
                {
                    "symbol": symbol,
                    "bucket_epoch": bucket_epoch,
                    "ist_time": epoch_to_ist_text(bucket_epoch),
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                }
            )

        append_rows_to_csv(csv_file, rows)

        print(
            f"BACKFILL {resolution}: filled={len(gap_df)} "
            f"from={epoch_to_ist_text(missing_from)} to={epoch_to_ist_text(missing_to)}",
            flush=True,
        )

    return gap_df


def main() -> None:
    broker = Broker()

    stream = MarketStream(symbols=[SYMBOL])
    stream.start()

    time.sleep(5)

    candle_5s = CandleManager(timeframe_seconds=5)
    candle_1m = CandleManager(timeframe_seconds=60)

    csv_5s = sync_csv_from_history(
        broker=broker,
        symbol=SYMBOL,
        resolution="5S",
        timeframe_seconds=5,
        csv_file="candles_5s.csv",
        default_lookback_seconds=15 * 60,
    )
    csv_1m = sync_csv_from_history(
        broker=broker,
        symbol=SYMBOL,
        resolution="1",
        timeframe_seconds=60,
        csv_file="candles_1m.csv",
        default_lookback_seconds=60 * 60,
    )

    seeded_5s = seed_manager_from_csv(
        manager=candle_5s,
        csv_df=csv_5s,
        symbol=SYMBOL,
        timeframe_seconds=5,
    )
    seeded_1m = seed_manager_from_csv(
        manager=candle_1m,
        csv_df=csv_1m,
        symbol=SYMBOL,
        timeframe_seconds=60,
    )

    print(f"SEEDED 5S FROM CSV: {seeded_5s}", flush=True)
    print(f"SEEDED 1M FROM CSV: {seeded_1m}", flush=True)

    startup_epoch = int(time.time())
    candle_5s.set_startup_epoch(startup_epoch)
    candle_1m.set_startup_epoch(startup_epoch)

    candle_runner = CandleRunner(
        tick_queue=stream.tick_queue,
        candle_managers={
            "5s": candle_5s,
            "1m": candle_1m,
        },
        poll_interval=0.05,
    )
    candle_runner.start()

    print("STARTING MARKET STREAM", flush=True)
    print("SYMBOL:", SYMBOL, flush=True)
    print("TIMEFRAMES: 5s, 1m", flush=True)
    print("STARTUP IST:", epoch_to_ist_text(startup_epoch), flush=True)

    last_written_5s = get_last_csv_bucket("candles_5s.csv", SYMBOL)
    last_written_1m = get_last_csv_bucket("candles_1m.csv", SYMBOL)

    try:
        while True:
            candles_5s = candle_runner.pop_closed_candles("5s")
            for candle in candles_5s:
                if last_written_5s is not None and candle.bucket_epoch > last_written_5s + 5:
                    gap_df = backfill_gap_to_csv(
                        broker=broker,
                        symbol=SYMBOL,
                        resolution="5S",
                        timeframe_seconds=5,
                        csv_file="candles_5s.csv",
                        last_bucket=last_written_5s,
                        next_live_bucket=candle.bucket_epoch,
                    )
                    if not gap_df.empty:
                        last_written_5s = int(gap_df.iloc[-1]["timestamp"])

                if last_written_5s is None or candle.bucket_epoch > last_written_5s:
                    append_candle_to_csv("candles_5s.csv", candle)
                    last_written_5s = candle.bucket_epoch

            candles_1m = candle_runner.pop_closed_candles("1m")
            for candle in candles_1m:
                if last_written_1m is not None and candle.bucket_epoch > last_written_1m + 60:
                    gap_df = backfill_gap_to_csv(
                        broker=broker,
                        symbol=SYMBOL,
                        resolution="1",
                        timeframe_seconds=60,
                        csv_file="candles_1m.csv",
                        last_bucket=last_written_1m,
                        next_live_bucket=candle.bucket_epoch,
                    )
                    if not gap_df.empty:
                        last_written_1m = int(gap_df.iloc[-1]["timestamp"])

                if last_written_1m is None or candle.bucket_epoch > last_written_1m:
                    append_candle_to_csv("candles_1m.csv", candle)
                    last_written_1m = candle.bucket_epoch

            time.sleep(0.1)

    except KeyboardInterrupt:
        candle_runner.stop()
        print("\nSTOPPING SYSTEM...", flush=True)


if __name__ == "__main__":
    main()