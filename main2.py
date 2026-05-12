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
from trading_app.broker.symbol_list import nifty_50
from trading_app.models import LiveCandle


SYMBOLS = nifty_50
IST = ZoneInfo("Asia/Kolkata")

MIN_5S_CANDLES = 180
STARTUP_HISTORY_REQUEST_DELAY = float(
    os.getenv("STARTUP_HISTORY_REQUEST_DELAY", "0.35")
)
LIVE_STATUS_INTERVAL_SECONDS = float(
    os.getenv("LIVE_STATUS_INTERVAL_SECONDS", "5")
)
GAP_BACKFILL_RETRY_COUNT = int(os.getenv("GAP_BACKFILL_RETRY_COUNT", "3"))
GAP_BACKFILL_RETRY_DELAY = float(os.getenv("GAP_BACKFILL_RETRY_DELAY", "1"))
REPAIR_1M_INTERVAL_SECONDS = float(os.getenv("REPAIR_1M_INTERVAL_SECONDS", "60"))
REPAIR_1M_LOOKBACK_MINUTES = int(os.getenv("REPAIR_1M_LOOKBACK_MINUTES", "10"))
REPAIR_1M_USE_API = os.getenv("REPAIR_1M_USE_API", "1") == "1"
REPAIR_1M_START_DELAY_SECONDS = float(
    os.getenv("REPAIR_1M_START_DELAY_SECONDS", "120")
)
REPAIR_1M_API_MIN_AGE_SECONDS = float(
    os.getenv("REPAIR_1M_API_MIN_AGE_SECONDS", "90")
)
STREAM_STALE_RESTART_SECONDS = float(
    os.getenv("STREAM_STALE_RESTART_SECONDS", "25")
)


def epoch_to_ist_text(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, IST).strftime("%Y-%m-%d %H:%M:%S")


def candle_to_row(candle: LiveCandle) -> dict:
    bucket_close_epoch = candle.bucket_epoch + candle.timeframe_seconds

    return {
        "symbol": candle.symbol,
        "bucket_epoch": candle.bucket_epoch,
        "ist_time": epoch_to_ist_text(candle.bucket_epoch),
        "bucket_close_ist": epoch_to_ist_text(bucket_close_epoch),
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


def append_history_5s_rows_to_csv(
    *,
    csv_file: str,
    symbol: str,
    hist_df: pd.DataFrame,
    existing_buckets: set[int],
) -> list[dict]:
    if hist_df.empty:
        return []

    rows: list[dict] = []

    for row in hist_df.itertuples(index=False):
        bucket_epoch = int(row.timestamp)
        if bucket_epoch in existing_buckets:
            continue

        rows.append(
            {
                "symbol": symbol,
                "bucket_epoch": bucket_epoch,
                "ist_time": epoch_to_ist_text(bucket_epoch),
                "bucket_close_ist": epoch_to_ist_text(bucket_epoch + 5),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
            }
        )

        existing_buckets.add(bucket_epoch)

    append_rows_to_csv(csv_file, rows)
    return rows


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


def build_1m_candle_from_5s_df(
    *,
    symbol: str,
    bucket_epoch: int,
    five_s_df: pd.DataFrame,
) -> LiveCandle | None:
    expected_buckets = {
        bucket_epoch + (index * 5)
        for index in range(12)
    }

    rows = five_s_df[
        (five_s_df["symbol"] == symbol)
        & (five_s_df["bucket_epoch"].isin(expected_buckets))
    ].copy()

    if rows.empty:
        return None

    rows = (
        rows.sort_values("bucket_epoch")
        .drop_duplicates(subset=["symbol", "bucket_epoch"], keep="last")
        .reset_index(drop=True)
    )

    if set(rows["bucket_epoch"].astype(int)) != expected_buckets:
        return None

    return LiveCandle(
        symbol=symbol,
        bucket_epoch=bucket_epoch,
        timeframe_seconds=60,
        open=float(rows.iloc[0]["open"]),
        high=float(rows["high"].max()),
        low=float(rows["low"].min()),
        close=float(rows.iloc[-1]["close"]),
        volume=0,
        is_complete=True,
    )


def get_existing_1m_keys(one_m_csv: str) -> set[tuple[str, int]]:
    try:
        one_m_df = pd.read_csv(one_m_csv)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return set()

    if one_m_df.empty or "symbol" not in one_m_df.columns:
        return set()

    one_m_df = one_m_df.copy()
    one_m_df["bucket_epoch"] = one_m_df["bucket_epoch"].astype(int)
    return set(zip(one_m_df["symbol"], one_m_df["bucket_epoch"]))


def append_missing_1m_from_5s_csv(
    *,
    symbols: list[str],
    five_s_csv: str,
    one_m_csv: str,
    min_minute_epoch: int | None = None,
    max_minute_epoch: int | None = None,
    log_prefix: str = "1M CSV BUILD",
) -> int:
    try:
        five_s_df = pd.read_csv(five_s_csv)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return 0

    if five_s_df.empty or "symbol" not in five_s_df.columns:
        return 0

    five_s_df = five_s_df.copy()
    five_s_df["bucket_epoch"] = five_s_df["bucket_epoch"].astype(int)
    five_s_df = (
        five_s_df.sort_values("bucket_epoch")
        .drop_duplicates(subset=["symbol", "bucket_epoch"], keep="last")
        .reset_index(drop=True)
    )
    five_s_df["minute_bucket"] = (five_s_df["bucket_epoch"] // 60) * 60

    existing_1m_keys = get_existing_1m_keys(one_m_csv)
    rows: list[dict] = []

    for symbol in symbols:
        symbol_5s_df = five_s_df[five_s_df["symbol"] == symbol]

        if symbol_5s_df.empty:
            continue

        minute_buckets = sorted(symbol_5s_df["minute_bucket"].unique())

        for minute_bucket in minute_buckets:
            minute_bucket = int(minute_bucket)

            if min_minute_epoch is not None and minute_bucket < min_minute_epoch:
                continue

            if max_minute_epoch is not None and minute_bucket > max_minute_epoch:
                continue

            one_m_key = (symbol, minute_bucket)

            if one_m_key in existing_1m_keys:
                continue

            candle = build_1m_candle_from_5s_df(
                symbol=symbol,
                bucket_epoch=minute_bucket,
                five_s_df=five_s_df,
            )

            if candle is None:
                continue

            rows.append(candle_to_row(candle))
            existing_1m_keys.add(one_m_key)

    rows.sort(key=lambda row: (int(row["bucket_epoch"]), str(row["symbol"])))
    append_rows_to_csv(one_m_csv, rows)

    if rows:
        first_bucket = min(int(row["bucket_epoch"]) for row in rows)
        last_bucket = max(int(row["bucket_epoch"]) for row in rows)
        print(
            f"{log_prefix}:",
            f"built_1m={len(rows)}",
            f"from={epoch_to_ist_text(first_bucket)}",
            f"to={epoch_to_ist_text(last_bucket)}",
            flush=True,
        )

    return len(rows)


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
    last_csv_bucket = (
        None if existing_df.empty else int(existing_df.iloc[-1]["bucket_epoch"])
    )

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
            earliest_needed_bucket = range_to_epoch - (
                (min_required_count - 1) * timeframe_seconds
            )
            existing_first_bucket = int(existing_df.iloc[0]["bucket_epoch"])
            range_from_epoch = min(existing_first_bucket, earliest_needed_bucket)
            range_from_epoch = max(0, range_from_epoch)

    print(
        f"CSV SYNC START {resolution}: symbol={symbol} "
        f"from={epoch_to_ist_text(range_from_epoch)} "
        f"to={epoch_to_ist_text(range_to_epoch)}",
        flush=True,
    )

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
            bucket_close_epoch = bucket_epoch + timeframe_seconds

            rows.append(
                {
                    "symbol": symbol,
                    "bucket_epoch": bucket_epoch,
                    "ist_time": epoch_to_ist_text(bucket_epoch),
                    "bucket_close_ist": epoch_to_ist_text(bucket_close_epoch),
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
        f"CSV SYNC {resolution}: symbol={symbol} "
        f"existing_last={last_csv_bucket} fetched={len(hist_df)} "
        f"final_count={len(updated_df)}",
        flush=True,
    )

    if not updated_df.empty:
        first_bucket = int(updated_df.iloc[0]["bucket_epoch"])
        last_bucket = int(updated_df.iloc[-1]["bucket_epoch"])
        print(
            f"CSV SYNC {resolution} RANGE: {symbol} "
            f"{epoch_to_ist_text(first_bucket)} -> {epoch_to_ist_text(last_bucket)}",
            flush=True,
        )

    return updated_df


def catch_up_5s_history_to_common_bucket(
    *,
    broker: Broker,
    symbols: list[str],
    csv_file: str,
    csv_5s_by_symbol: dict[str, pd.DataFrame],
) -> int:
    range_to_epoch = broker.get_completed_range_to_epoch(resolution="5S")
    target_bucket = (range_to_epoch // 5) * 5
    total_filled = 0

    print(
        "STARTUP COMMON 5S CATCHUP:",
        f"target={epoch_to_ist_text(target_bucket)}",
        flush=True,
    )

    for index, symbol in enumerate(symbols, start=1):
        existing_df = read_existing_csv(csv_file, symbol)
        last_bucket = (
            None if existing_df.empty else int(existing_df.iloc[-1]["bucket_epoch"])
        )

        if last_bucket is not None and last_bucket >= target_bucket:
            csv_5s_by_symbol[symbol] = existing_df.tail(MIN_5S_CANDLES)
            continue

        range_from_epoch = 0 if last_bucket is None else last_bucket + 5

        hist_df = fetch_history_range(
            broker=broker,
            symbol=symbol,
            resolution="5S",
            range_from_epoch=range_from_epoch,
            range_to_epoch=range_to_epoch,
        )

        existing_buckets = (
            set()
            if existing_df.empty
            else set(existing_df["bucket_epoch"].astype(int))
        )
        new_rows = append_history_5s_rows_to_csv(
            csv_file=csv_file,
            symbol=symbol,
            hist_df=hist_df,
            existing_buckets=existing_buckets,
        )
        total_filled += len(new_rows)

        updated_df = read_existing_csv(csv_file, symbol).tail(MIN_5S_CANDLES)
        csv_5s_by_symbol[symbol] = updated_df

        if new_rows:
            print(
                f"STARTUP COMMON 5S CATCHUP {index}/{len(symbols)}:",
                f"symbol={symbol}",
                f"filled={len(new_rows)}",
                f"last={epoch_to_ist_text(int(updated_df.iloc[-1]['bucket_epoch']))}",
                flush=True,
            )

    print(
        "STARTUP COMMON 5S CATCHUP DONE:",
        f"filled={total_filled}",
        f"target={epoch_to_ist_text(target_bucket)}",
        flush=True,
    )

    return total_filled


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
    append_to_csv: bool = True,
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

    if not gap_df.empty and append_to_csv:
        rows: list[dict] = []

        for row in gap_df.itertuples(index=False):
            bucket_epoch = int(row.timestamp)
            bucket_close_epoch = bucket_epoch + timeframe_seconds

            rows.append(
                {
                    "symbol": symbol,
                    "bucket_epoch": bucket_epoch,
                    "ist_time": epoch_to_ist_text(bucket_epoch),
                    "bucket_close_ist": epoch_to_ist_text(bucket_close_epoch),
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                }
            )

        append_rows_to_csv(csv_file, rows)

    if not gap_df.empty:
        print(
            f"API GAP CALLBACK {resolution}: symbol={symbol} filled={len(gap_df)} "
            f"from={epoch_to_ist_text(missing_from)} to={epoch_to_ist_text(missing_to)}",
            flush=True,
        )

    return gap_df


def repair_recent_1m_from_5s(
    *,
    broker: Broker,
    symbols: list[str],
    five_s_csv: str,
    one_m_csv: str,
    now_epoch: int,
    lookback_minutes: int,
    use_api: bool,
    min_age_seconds: float = 0,
) -> tuple[int, int, int]:
    if lookback_minutes <= 0:
        return 0, 0, 0

    try:
        five_s_df = pd.read_csv(five_s_csv)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return 0, 0, 0

    if five_s_df.empty or "symbol" not in five_s_df.columns:
        return 0, 0, 0

    five_s_df = five_s_df.copy()
    five_s_df["bucket_epoch"] = five_s_df["bucket_epoch"].astype(int)

    try:
        one_m_df = pd.read_csv(one_m_csv)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        one_m_df = pd.DataFrame(columns=["symbol", "bucket_epoch"])

    if one_m_df.empty or "symbol" not in one_m_df.columns:
        existing_1m_keys: set[tuple[str, int]] = set()
    else:
        existing_1m_keys = get_existing_1m_keys(one_m_csv)

    repairable_epoch = int(now_epoch - min_age_seconds)
    latest_completed_minute = (repairable_epoch // 60) * 60 - 60
    earliest_minute = latest_completed_minute - ((lookback_minutes - 1) * 60)

    repaired_1m = 0
    filled_5s = 0
    incomplete_1m = 0

    for minute_bucket in range(earliest_minute, latest_completed_minute + 1, 60):
        for symbol in symbols:
            one_m_key = (symbol, minute_bucket)

            if one_m_key in existing_1m_keys:
                continue

            expected_buckets = set(range(minute_bucket, minute_bucket + 60, 5))
            symbol_5s_df = five_s_df[five_s_df["symbol"] == symbol]
            existing_5s_buckets = set(symbol_5s_df["bucket_epoch"].astype(int))
            missing_5s_buckets = expected_buckets - existing_5s_buckets

            if missing_5s_buckets and use_api:
                for attempt in range(1, GAP_BACKFILL_RETRY_COUNT + 1):
                    hist_df = fetch_history_range(
                        broker=broker,
                        symbol=symbol,
                        resolution="5S",
                        range_from_epoch=minute_bucket,
                        range_to_epoch=minute_bucket + 59,
                    )
                    new_rows = append_history_5s_rows_to_csv(
                        csv_file=five_s_csv,
                        symbol=symbol,
                        hist_df=hist_df,
                        existing_buckets=existing_5s_buckets,
                    )

                    if new_rows:
                        five_s_df = pd.concat(
                            [five_s_df, pd.DataFrame(new_rows)],
                            ignore_index=True,
                        )
                        filled_5s += len(new_rows)

                    symbol_5s_df = five_s_df[five_s_df["symbol"] == symbol]
                    existing_5s_buckets = set(
                        symbol_5s_df["bucket_epoch"].astype(int)
                    )
                    missing_5s_buckets = expected_buckets - existing_5s_buckets

                    if not missing_5s_buckets:
                        break

                    if attempt < GAP_BACKFILL_RETRY_COUNT:
                        time.sleep(GAP_BACKFILL_RETRY_DELAY)

            candle = build_1m_candle_from_5s_df(
                symbol=symbol,
                bucket_epoch=minute_bucket,
                five_s_df=five_s_df,
            )

            if candle is None:
                incomplete_1m += 1
                continue

            append_candle_to_csv(one_m_csv, candle)
            existing_1m_keys.add(one_m_key)
            repaired_1m += 1

            print(
                "1M REPAIRED:",
                f"symbol={symbol}",
                f"open={epoch_to_ist_text(minute_bucket)}",
                f"close={epoch_to_ist_text(minute_bucket + 60)}",
                flush=True,
            )

    if repaired_1m or filled_5s or incomplete_1m:
        print(
            "1M REPAIR STATUS:",
            f"filled_5s={filled_5s}",
            f"repaired_1m={repaired_1m}",
            f"incomplete_1m={incomplete_1m}",
            f"lookback_minutes={lookback_minutes}",
            flush=True,
        )

    return repaired_1m, filled_5s, incomplete_1m


def main() -> None:
    broker = Broker()
    stream = MarketStream(symbols=SYMBOLS)
    stream.start()

    csv_5s_by_symbol: dict[str, pd.DataFrame] = {}

    print(
        f"STARTUP HISTORY SYNC: symbols={len(SYMBOLS)} "
        f"delay={STARTUP_HISTORY_REQUEST_DELAY}s",
        flush=True,
    )
    print("MARKET STREAM STARTED EARLY", flush=True)

    for index, symbol in enumerate(SYMBOLS, start=1):
        print(
            f"STARTUP HISTORY SYMBOL {index}/{len(SYMBOLS)}: {symbol}",
            flush=True,
        )
        csv_5s_by_symbol[symbol] = sync_csv_from_history(
            broker=broker,
            symbol=symbol,
            resolution="5S",
            timeframe_seconds=5,
            csv_file="candles_5s.csv",
            default_lookback_seconds=15 * 60,
            min_required_count=MIN_5S_CANDLES,
        )

        if index < len(SYMBOLS) and STARTUP_HISTORY_REQUEST_DELAY > 0:
            time.sleep(STARTUP_HISTORY_REQUEST_DELAY)

    startup_catchup_5s = catch_up_5s_history_to_common_bucket(
        broker=broker,
        symbols=SYMBOLS,
        csv_file="candles_5s.csv",
        csv_5s_by_symbol=csv_5s_by_symbol,
    )

    startup_epoch = int(time.time())
    startup_completed_5s_bucket = (startup_epoch // 5) * 5 - 5

    candle_5s = CandleManager(
        timeframe_seconds=5,
        startup_epoch=startup_epoch,
        allow_partial_bucket=True,
        close_grace_seconds=1,
    )
    candle_1m = CandleManager(
        timeframe_seconds=60,
        startup_epoch=startup_epoch,
        allow_partial_bucket=False,
    )

    candle_5s.downstream_managers.append(candle_1m)

    pending_gap_requests: set[tuple[str, int, int, int]] = set()

    def on_5s_gap_detected(
        symbol: str,
        from_epoch: int,
        to_epoch: int,
        timeframe_seconds: int,
    ) -> bool:
        gap_key = (
            symbol,
            from_epoch,
            to_epoch,
            timeframe_seconds,
        )

        if gap_key in pending_gap_requests:
            return False

        pending_gap_requests.add(gap_key)

        try:
            expected_buckets = set(range(from_epoch, to_epoch + 1, timeframe_seconds))
            gap_df = pd.DataFrame()

            for attempt in range(1, GAP_BACKFILL_RETRY_COUNT + 1):
                gap_df = backfill_gap_to_csv(
                    broker=broker,
                    symbol=symbol,
                    resolution="5S",
                    timeframe_seconds=timeframe_seconds,
                    csv_file="candles_5s.csv",
                    last_bucket=from_epoch - timeframe_seconds,
                    next_live_bucket=to_epoch + timeframe_seconds,
                    append_to_csv=False,
                )

                fetched_buckets = (
                    set() if gap_df.empty else set(gap_df["timestamp"].astype(int))
                )

                if expected_buckets.issubset(fetched_buckets):
                    break

                if attempt < GAP_BACKFILL_RETRY_COUNT:
                    time.sleep(GAP_BACKFILL_RETRY_DELAY)

            if gap_df.empty:
                print(
                    "API GAP INCOMPLETE:",
                    f"symbol={symbol}",
                    f"from={epoch_to_ist_text(from_epoch)}",
                    f"to={epoch_to_ist_text(to_epoch)}",
                    "fetched=0",
                    flush=True,
                )
                return False

            fetched_buckets = set(gap_df["timestamp"].astype(int))
            missing_buckets = sorted(expected_buckets - fetched_buckets)

            if missing_buckets:
                print(
                    "API GAP INCOMPLETE:",
                    f"symbol={symbol}",
                    f"missing={len(missing_buckets)}",
                    f"first_missing={epoch_to_ist_text(missing_buckets[0])}",
                    flush=True,
                )
                return False

            gap_df = gap_df.rename(columns={"timestamp": "bucket_epoch"})

            gap_candles = build_live_candles_from_csv(
                gap_df,
                symbol=symbol,
                timeframe_seconds=timeframe_seconds,
            )

            for gap_candle in gap_candles:
                candle_5s.replay_closed_candle(gap_candle)

            return True

        finally:
            pending_gap_requests.discard(gap_key)

    candle_5s.set_gap_callback(on_5s_gap_detected)

    seeded_5s_total = 0
    replayed_5s_total = 0
    replay_cutoff_epoch = startup_completed_5s_bucket

    for symbol, csv_5s in csv_5s_by_symbol.items():
        seeded_5s_total += seed_manager_from_csv(
            manager=candle_5s,
            csv_df=csv_5s,
            symbol=symbol,
            timeframe_seconds=5,
        )

        seeded_5s_candles = build_live_candles_from_csv(
            csv_5s,
            symbol=symbol,
            timeframe_seconds=5,
        )

        for candle in seeded_5s_candles:
            candle_close_epoch = candle.bucket_epoch + candle.timeframe_seconds

            if candle_close_epoch <= replay_cutoff_epoch:
                candle_1m.aggregate_closed_candle(candle)
                replayed_5s_total += 1

    replayed_1m_candles = candle_1m.pop_closed_candles()

    last_written_1m_by_symbol = {
        symbol: get_last_csv_bucket("candles_1m.csv", symbol)
        for symbol in SYMBOLS
    }

    for candle in replayed_1m_candles:
        last_written = last_written_1m_by_symbol.get(candle.symbol)

        if last_written is None or candle.bucket_epoch > last_written:
            append_candle_to_csv("candles_1m.csv", candle)
            last_written_1m_by_symbol[candle.symbol] = candle.bucket_epoch

    built_1m_from_5s_csv = append_missing_1m_from_5s_csv(
        symbols=SYMBOLS,
        five_s_csv="candles_5s.csv",
        one_m_csv="candles_1m.csv",
        log_prefix="STARTUP 1M CSV BUILD",
    )

    if built_1m_from_5s_csv:
        last_written_1m_by_symbol = {
            symbol: get_last_csv_bucket("candles_1m.csv", symbol)
            for symbol in SYMBOLS
        }

    print(f"SEEDED 5S FROM CSV: {seeded_5s_total}", flush=True)
    print(f"REPLAYED 5S TO 1M: {replayed_5s_total}", flush=True)
    print(f"SEEDED 1M FROM 5S REPLAY: {len(replayed_1m_candles)}", flush=True)
    print(f"BUILT 1M FROM 5S CSV: {built_1m_from_5s_csv}", flush=True)
    print(f"STARTUP CATCHUP 5S FILLED: {startup_catchup_5s}", flush=True)
    print("QUEUED TICKS BEFORE RUNNER:", stream.tick_queue.qsize(), flush=True)

    candle_runner = CandleRunner(
        tick_queue=stream.tick_queue,
        candle_managers={"5s": candle_5s},
        poll_interval=0.05,
    )
    candle_runner.start()

    print("STARTING MARKET STREAM", flush=True)
    print("SYMBOL COUNT:", len(SYMBOLS), flush=True)
    print("TIMEFRAMES: 5s, 1m", flush=True)
    print("STARTUP IST:", epoch_to_ist_text(startup_epoch), flush=True)
    print("STREAM THREAD ALIVE:", stream.is_alive(), flush=True)
    print("STREAM CONNECTED:", stream.is_connected(), flush=True)

    last_written_5s_by_symbol = {
        symbol: get_last_csv_bucket("candles_5s.csv", symbol)
        for symbol in SYMBOLS
    }

    total_written_5s = 0
    total_written_1m = 0
    runner_start_time = time.time()
    last_status_time = runner_start_time
    last_status_total_5s = 0
    last_status_total_1m = 0
    last_status_raw_messages = 0
    last_status_tick_messages = 0
    last_repair_time = runner_start_time
    repair_start_time = runner_start_time + REPAIR_1M_START_DELAY_SECONDS
    last_immediate_repair_minute: int | None = None

    try:
        while True:
            candles_5s = candle_runner.pop_closed_candles("5s")
            written_5s = 0
            written_5s_buckets: list[int] = []

            for candle in candles_5s:
                last_written = last_written_5s_by_symbol.get(candle.symbol)

                if last_written is None or candle.bucket_epoch > last_written:
                    append_candle_to_csv("candles_5s.csv", candle)
                    last_written_5s_by_symbol[candle.symbol] = candle.bucket_epoch
                    written_5s += 1
                    written_5s_buckets.append(candle.bucket_epoch)

            total_written_5s += written_5s

            candles_1m = candle_1m.pop_closed_candles()
            written_1m = 0

            for candle in candles_1m:
                last_written = last_written_1m_by_symbol.get(candle.symbol)

                if last_written is None or candle.bucket_epoch > last_written:
                    append_candle_to_csv("candles_1m.csv", candle)
                    last_written_1m_by_symbol[candle.symbol] = candle.bucket_epoch
                    written_1m += 1
                    print(
                        "1M CLOSED:",
                        f"symbol={candle.symbol}",
                        f"open={epoch_to_ist_text(candle.bucket_epoch)}",
                        f"close={epoch_to_ist_text(candle.bucket_epoch + candle.timeframe_seconds)}",
                        f"O={candle.open} H={candle.high} L={candle.low} C={candle.close}",
                        flush=True,
                    )

            total_written_1m += written_1m

            fallback_written_1m = 0
            immediate_repaired_1m = 0
            immediate_repaired_5s = 0

            if written_5s_buckets:
                min_minute_epoch = (min(written_5s_buckets) // 60) * 60
                max_minute_epoch = (max(written_5s_buckets) // 60) * 60
                fallback_written_1m = append_missing_1m_from_5s_csv(
                    symbols=SYMBOLS,
                    five_s_csv="candles_5s.csv",
                    one_m_csv="candles_1m.csv",
                    min_minute_epoch=min_minute_epoch,
                    max_minute_epoch=max_minute_epoch,
                    log_prefix="LIVE 1M CSV FALLBACK",
                )

                if fallback_written_1m:
                    total_written_1m += fallback_written_1m
                    last_written_1m_by_symbol = {
                        symbol: get_last_csv_bucket("candles_1m.csv", symbol)
                        for symbol in SYMBOLS
                    }

            now = time.time()
            stream_restarted = False

            if stream.should_restart(stale_after_seconds=STREAM_STALE_RESTART_SECONDS):
                stream_age = stream.message_age()
                reason = (
                    "stale_messages"
                    if stream_age is not None
                    and stream_age >= STREAM_STALE_RESTART_SECONDS
                    else "disconnected"
                )
                stream_restarted = stream.restart(reason)

            minute_close_buckets = [
                bucket_epoch
                for bucket_epoch in written_5s_buckets
                if bucket_epoch % 60 == 55
            ]

            if minute_close_buckets:
                latest_closed_minute = (max(minute_close_buckets) // 60) * 60

                if latest_closed_minute != last_immediate_repair_minute:
                    (
                        immediate_repaired_1m,
                        immediate_repaired_5s,
                        _,
                    ) = repair_recent_1m_from_5s(
                        broker=broker,
                        symbols=SYMBOLS,
                        five_s_csv="candles_5s.csv",
                        one_m_csv="candles_1m.csv",
                        now_epoch=int(now),
                        lookback_minutes=2,
                        use_api=False,
                    )

                    if immediate_repaired_5s:
                        last_written_5s_by_symbol = {
                            symbol: get_last_csv_bucket("candles_5s.csv", symbol)
                            for symbol in SYMBOLS
                        }

                    if immediate_repaired_1m:
                        total_written_1m += immediate_repaired_1m
                        last_written_1m_by_symbol = {
                            symbol: get_last_csv_bucket("candles_1m.csv", symbol)
                            for symbol in SYMBOLS
                        }

                    last_repair_time = now
                    last_immediate_repair_minute = latest_closed_minute

            if (
                now >= repair_start_time
                and now - last_repair_time >= REPAIR_1M_INTERVAL_SECONDS
            ):
                repaired_1m, repaired_5s, _ = repair_recent_1m_from_5s(
                    broker=broker,
                    symbols=SYMBOLS,
                    five_s_csv="candles_5s.csv",
                    one_m_csv="candles_1m.csv",
                    now_epoch=int(now),
                    lookback_minutes=REPAIR_1M_LOOKBACK_MINUTES,
                    use_api=REPAIR_1M_USE_API,
                    min_age_seconds=REPAIR_1M_API_MIN_AGE_SECONDS,
                )

                if repaired_5s:
                    last_written_5s_by_symbol = {
                        symbol: get_last_csv_bucket("candles_5s.csv", symbol)
                        for symbol in SYMBOLS
                    }

                if repaired_1m:
                    total_written_1m += repaired_1m
                    last_written_1m_by_symbol = {
                        symbol: get_last_csv_bucket("candles_1m.csv", symbol)
                        for symbol in SYMBOLS
                    }

                last_repair_time = now

            if now - last_status_time >= LIVE_STATUS_INTERVAL_SECONDS:
                interval_5s = total_written_5s - last_status_total_5s
                interval_1m = total_written_1m - last_status_total_1m
                interval_raw = stream.raw_message_count - last_status_raw_messages
                interval_ticks = (
                    stream.tick_message_count - last_status_tick_messages
                )
                last_msg_age = (
                    None
                    if stream.last_message_time is None
                    else round(now - stream.last_message_time, 2)
                )

                print(
                    "LIVE STATUS:",
                    f"stream_connected={stream.is_connected()}",
                    f"tick_queue={stream.tick_queue.qsize()}",
                    f"last_msg_age={last_msg_age}",
                    f"interval_raw={interval_raw}",
                    f"interval_ticks={interval_ticks}",
                    f"latest_ticks={stream.latest_tick_count()}",
                    f"interval_5s={interval_5s}",
                    f"interval_1m={interval_1m}",
                    f"loop_5s={written_5s}",
                    f"loop_1m={written_1m}",
                    f"loop_fallback_1m={fallback_written_1m}",
                    f"immediate_1m={immediate_repaired_1m}",
                    f"immediate_5s={immediate_repaired_5s}",
                    f"stream_restarts={stream.restart_count}",
                    f"stream_restarted={stream_restarted}",
                    f"total_5s={total_written_5s}",
                    f"total_1m={total_written_1m}",
                    flush=True,
                )
                last_status_time = now
                last_status_total_5s = total_written_5s
                last_status_total_1m = total_written_1m
                last_status_raw_messages = stream.raw_message_count
                last_status_tick_messages = stream.tick_message_count

            time.sleep(0.1)

    except KeyboardInterrupt:
        candle_runner.stop()
        stream.stop()
        print("\nSTOPPING SYSTEM...", flush=True)


if __name__ == "__main__":
    main()
