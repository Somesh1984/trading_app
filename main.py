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

MIN_5S_CANDLES = 180


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
    min_required_count: int,
) -> pd.DataFrame:
    existing_df = read_existing_csv(csv_file, symbol)
    last_csv_bucket = None if existing_df.empty else int(existing_df.iloc[-1]["bucket_epoch"])

    range_to_epoch = broker.get_completed_range_to_epoch(resolution=resolution)

    target_lookback_seconds = max(
        default_lookback_seconds,
        min_required_count * timeframe_seconds,
    )

    if last_csv_bucket is None:
        range_from_epoch = max(0, range_to_epoch - target_lookback_seconds + 1)
    else:
        existing_count = len(existing_df)

        if existing_count >= min_required_count:
            range_from_epoch = last_csv_bucket + timeframe_seconds
        else:
            earliest_needed_bucket = range_to_epoch - ((min_required_count - 1) * timeframe_seconds)
            existing_first_bucket = int(existing_df.iloc[0]["bucket_epoch"])
            range_from_epoch = min(existing_first_bucket, earliest_needed_bucket)
            range_from_epoch = max(0, range_from_epoch)

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

    if len(updated_df) > min_required_count:
        updated_df = updated_df.tail(min_required_count).reset_index(drop=True)

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

    csv_5s = sync_csv_from_history(
        broker=broker,
        symbol=SYMBOL,
        resolution="5S",
        timeframe_seconds=5,
        csv_file="candles_5s.csv",
        default_lookback_seconds=15 * 60,
        min_required_count=MIN_5S_CANDLES,
    )

    startup_epoch = int(time.time())

    candle_5s = CandleManager(
        timeframe_seconds=5,
        startup_epoch=startup_epoch,
        allow_partial_bucket=True,
    )
    candle_1m = CandleManager(
        timeframe_seconds=60,
        startup_epoch=startup_epoch,
        allow_partial_bucket=False,
    )

    candle_5s.downstream_managers.append(candle_1m)

    seeded_5s = seed_manager_from_csv(
        manager=candle_5s,
        csv_df=csv_5s,
        symbol=SYMBOL,
        timeframe_seconds=5,
    )

    seeded_5s_candles = build_live_candles_from_csv(
        csv_5s,
        symbol=SYMBOL,
        timeframe_seconds=5,
    )

    # startup ke time current 1m partial ho sakti hai, isliye
    # us minute ke start se jitni completed 5s candles available hain
    # unko replay karo. current open 5s bucket replay mat karo.
    replay_cutoff_epoch = startup_epoch - 1

    replayed_5s_for_1m: list[LiveCandle] = []
    for candle in seeded_5s_candles:
        candle_close_epoch = candle.bucket_epoch + candle.timeframe_seconds
        if candle_close_epoch <= replay_cutoff_epoch:
            candle_1m.aggregate_closed_candle(candle)
            replayed_5s_for_1m.append(candle)

    replayed_1m_candles = candle_1m.pop_closed_candles()
    last_written_1m = get_last_csv_bucket("candles_1m.csv", SYMBOL)

    for candle in replayed_1m_candles:
        if last_written_1m is None or candle.bucket_epoch > last_written_1m:
            append_candle_to_csv("candles_1m.csv", candle)
            last_written_1m = candle.bucket_epoch

    seeded_1m = len(replayed_1m_candles)

    print(f"SEEDED 5S FROM CSV: {seeded_5s}", flush=True)
    print(f"REPLAYED 5S TO 1M: {len(replayed_5s_for_1m)}", flush=True)
    print(f"SEEDED 1M FROM 5S REPLAY: {seeded_1m}", flush=True)

    stream = MarketStream(symbols=[SYMBOL])
    stream.start()

    time.sleep(1)

    candle_runner = CandleRunner(
        tick_queue=stream.tick_queue,
        candle_managers={"5s": candle_5s},
        poll_interval=0.05,
    )
    candle_runner.start()

    print("STARTING MARKET STREAM", flush=True)
    print("SYMBOL:", SYMBOL, flush=True)
    print("TIMEFRAMES: 5s, 1m", flush=True)
    print("STARTUP IST:", epoch_to_ist_text(startup_epoch), flush=True)

    last_written_5s = get_last_csv_bucket("candles_5s.csv", SYMBOL)
    if last_written_1m is None:
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

            candles_1m = candle_1m.pop_closed_candles()
            for candle in candles_1m:
                print(
                    "1M CLOSED:",
                    f"open={epoch_to_ist_text(candle.bucket_epoch)}",
                    f"close={epoch_to_ist_text(candle.bucket_epoch + candle.timeframe_seconds)}",
                    f"O={candle.open} H={candle.high} L={candle.low} C={candle.close}",
                    flush=True,
                )

                if last_written_1m is None or candle.bucket_epoch > last_written_1m:
                    append_candle_to_csv("candles_1m.csv", candle)
                    last_written_1m = candle.bucket_epoch

            time.sleep(0.1)

    except KeyboardInterrupt:
        candle_runner.stop()
        print("\nSTOPPING SYSTEM...", flush=True)


if __name__ == "__main__":
    main()