from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import date, datetime
from io import StringIO
from pathlib import Path

import requests

from ..models import (FyersBaseSymbol,FyersEquitySymbol,FyersFutureSymbol,FyersIndexSpotSymbol,FyersOptionSymbol,)


class FyersSymbolService:
    SYMBOL_MASTER_URLS: dict[str, str] = {
        "NSE_CM": "https://public.fyers.in/sym_details/NSE_CM.csv",
        "BSE_CM": "https://public.fyers.in/sym_details/BSE_CM.csv",
        "NSE_FO": "https://public.fyers.in/sym_details/NSE_FO.csv",
        "BSE_FO": "https://public.fyers.in/sym_details/BSE_FO.csv",
    }

    def __init__(self, cache_path: str | None = None) -> None:
        self.cache_path = Path(cache_path) if cache_path else self.build_dated_cache_path()

    @staticmethod
    def build_dated_cache_path(as_of: date | None = None, base_dir: str = "data/symbols") -> Path:
        current_date = as_of or date.today()
        return Path(base_dir) / f"{current_date.strftime('%Y%m%d')}_symbols.json"

    def set_cache_for_date(self, as_of: date | None = None, *, base_dir: str = "data/symbols") -> Path:
        self.cache_path = self.build_dated_cache_path(as_of=as_of, base_dir=base_dir)
        return self.cache_path

    def fetch_symbol_master(self,exchanges: list[str] | None = None,*,timeout: int = 60,) -> list[FyersBaseSymbol]:
        selected_exchanges = exchanges or list(self.SYMBOL_MASTER_URLS.keys())
        all_symbols: list[FyersBaseSymbol] = []

        for exchange_key in selected_exchanges:
            url = self.SYMBOL_MASTER_URLS.get(exchange_key)
            if not url:
                raise ValueError(f"Unsupported exchange key: {exchange_key}")

            response = requests.get(url, timeout=timeout)
            response.raise_for_status()

            if exchange_key.endswith("_CM"):
                exchange_symbols = self._parse_cm_csv(response.text)
            elif exchange_key.endswith("_FO"):
                exchange_symbols = self._parse_fo_csv(response.text)
            else:
                exchange_symbols = []

            all_symbols.extend(exchange_symbols)

        return self._dedupe_symbols(all_symbols)

    def refresh_cache(self,exchanges: list[str] | None = None,*,timeout: int = 60,) -> list[FyersBaseSymbol]:
        symbols = self.fetch_symbol_master(exchanges=exchanges, timeout=timeout)
        self.save_cache(symbols)
        return symbols

    def ensure_daily_cache(self,exchanges: list[str] | None = None,*,timeout: int = 60,force_refresh: bool = False,) -> list[FyersBaseSymbol]:
        if not force_refresh:
            cached = self.load_cache()
            if cached:
                return cached
        return self.refresh_cache(exchanges=exchanges, timeout=timeout)

    def save_cache(self, symbols: list[FyersBaseSymbol]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload: list[dict] = []

        for symbol in symbols:
            item = asdict(symbol)
            item["kind"] = symbol.kind
            payload.append(item)

        self.cache_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_cache(self) -> list[FyersBaseSymbol]:
        if not self.cache_path.exists() or not self.cache_path.is_file():
            return []

        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

        if not isinstance(raw, list):
            return []

        symbols: list[FyersBaseSymbol] = []

        for item in raw:
            if not isinstance(item, dict):
                continue

            kind = str(item.pop("kind", "")).strip()

            try:
                symbol = self._build_symbol_from_dict(kind, item)
            except TypeError:
                continue

            if symbol is not None:
                symbols.append(symbol)

        return symbols

    def search(self,query: str,*,limit: int = 50,use_cache_only: bool = True,) -> list[FyersBaseSymbol]:
        q = query.strip().lower()
        if not q:
            return []

        symbols = self.load_cache() if use_cache_only else self.fetch_symbol_master()
        results = [item for item in symbols if q in item.symbol.lower() or q in item.display_name.lower()]
        return results[:limit]

    def _parse_cm_csv(self, csv_text: str) -> list[FyersBaseSymbol]:
        rows = csv.reader(StringIO(csv_text))
        symbols: list[FyersBaseSymbol] = []

        for row in rows:
            if len(row) < 18:
                continue

            token = row[0].strip()
            display_name = row[1].strip()
            short_symbol = row[2].strip()
            lot_size = self._to_int(row[3])
            tick_size = self._to_float(row[4])
            isin = row[5].strip()
            trading_session = row[6].strip()
            last_updated = row[7].strip()
            symbol = row[9].strip()
            raw_exchange = row[10].strip()
            raw_segment = row[11].strip()
            script_code = row[12].strip()
            underlying_token = row[13].strip() if len(row) > 13 else ""

            if not symbol:
                continue

            exchange_code = self._map_exchange_code(raw_exchange)
            segment_code = self._map_segment_code(raw_segment)

            if symbol.endswith("-INDEX"):
                symbols.append(FyersIndexSpotSymbol(
                        symbol=symbol,
                        display_name=display_name,
                        exchange_code=exchange_code,
                        segment_code=segment_code,
                        token=token,
                        short_symbol=short_symbol,
                        lot_size=lot_size,
                        tick_size=tick_size,
                        last_updated=last_updated,
                        trading_session=trading_session,
                        fy_token_underlying=underlying_token,
                        raw_exchange=raw_exchange,
                        raw_segment=raw_segment,
                        script_code=script_code,))
            else:
                symbols.append(FyersEquitySymbol(
                        symbol=symbol,
                        display_name=display_name,
                        exchange_code=exchange_code,
                        segment_code=segment_code,
                        token=token,
                        short_symbol=short_symbol,
                        lot_size=lot_size,
                        tick_size=tick_size,
                        last_updated=last_updated,
                        trading_session=trading_session,
                        fy_token_underlying=underlying_token,
                        raw_exchange=raw_exchange,
                        raw_segment=raw_segment,
                        isin=isin,
                        script_code=script_code,))

        return symbols

    def _parse_fo_csv(self, csv_text: str) -> list[FyersBaseSymbol]:
        rows = csv.reader(StringIO(csv_text))
        symbols: list[FyersBaseSymbol] = []

        for row in rows:
            if len(row) < 18:
                continue

            token = row[0].strip()
            display_name = row[1].strip()
            short_symbol = row[2].strip()
            lot_size = self._to_int(row[3])
            tick_size = self._to_float(row[4])
            trading_session = row[6].strip()
            last_updated = row[7].strip()
            expiry_epoch = self._to_int(row[8])
            symbol = row[9].strip()
            raw_exchange = row[10].strip()
            raw_segment = row[11].strip()
            script_code = row[12].strip()
            underlying_token = row[13].strip() if len(row) > 13 else ""
            underlying_symbol = row[14].strip() if len(row) > 14 else ""
            strike = self._to_float(row[15]) if len(row) > 15 else 0.0
            option_type = row[16].strip() if len(row) > 16 else ""
            instrument_type = row[17].strip() if len(row) > 17 else ""

            if not symbol:
                continue

            exchange_code = self._map_exchange_code(raw_exchange)
            segment_code = self._map_segment_code(raw_segment)

            if option_type in {"CE", "PE"}:
                symbols.append(
                    FyersOptionSymbol(
                        symbol=symbol,
                        display_name=display_name,
                        exchange_code=exchange_code,
                        segment_code=segment_code,
                        token=token,
                        short_symbol=short_symbol,
                        lot_size=lot_size,
                        tick_size=tick_size,
                        last_updated=last_updated,
                        trading_session=trading_session,
                        fy_token_underlying=underlying_token,
                        raw_exchange=raw_exchange,
                        raw_segment=raw_segment,
                        underlying_symbol=underlying_symbol,
                        underlying_script_code=script_code,
                        expiry_epoch=expiry_epoch,
                        strike=strike,
                        option_type=option_type,
                        instrument_type=instrument_type,
                    )
                )
            else:
                symbols.append(
                    FyersFutureSymbol(
                        symbol=symbol,
                        display_name=display_name,
                        exchange_code=exchange_code,
                        segment_code=segment_code,
                        token=token,
                        short_symbol=short_symbol,
                        lot_size=lot_size,
                        tick_size=tick_size,
                        last_updated=last_updated,
                        trading_session=trading_session,
                        fy_token_underlying=underlying_token,
                        raw_exchange=raw_exchange,
                        raw_segment=raw_segment,
                        underlying_symbol=underlying_symbol,
                        underlying_script_code=script_code,
                        expiry_epoch=expiry_epoch,
                        instrument_type=instrument_type,
                    )
                )

        return symbols

    def _build_symbol_from_dict(self, kind: str, payload: dict) -> FyersBaseSymbol | None:
        if kind == "equity":
            return FyersEquitySymbol(**payload)
        if kind == "index_spot":
            return FyersIndexSpotSymbol(**payload)
        if kind == "future":
            return FyersFutureSymbol(**payload)
        if kind == "option":
            return FyersOptionSymbol(**payload)
        return None

    def _dedupe_symbols(self, symbols: list[FyersBaseSymbol]) -> list[FyersBaseSymbol]:
        unique: dict[str, FyersBaseSymbol] = {}
        for item in symbols:
            unique[item.symbol] = item
        return list(unique.values())

    @staticmethod
    def _to_int(value: str) -> int:
        value = value.strip()
        if not value:
            return 0
        try:
            return int(float(value))
        except ValueError:
            return 0

    @staticmethod
    def _to_float(value: str) -> float:
        value = value.strip()
        if not value:
            return 0.0
        try:
            return float(value)
        except ValueError:
            return 0.0

    @staticmethod
    def _map_exchange_code(raw_exchange: str) -> str:
        return {"10": "NSE", "12": "BSE"}.get(raw_exchange, raw_exchange)

    @staticmethod
    def _map_segment_code(raw_segment: str) -> str:
        return {"10": "CM", "11": "FO"}.get(raw_segment, raw_segment)

    @staticmethod
    def _normalize_underlying_text(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    def _matches_underlying(self, item: FyersBaseSymbol, underlying: str) -> bool:
        key = self._normalize_underlying_text(underlying)
        if not key:
            return False

        candidates = [item.symbol, item.display_name]
        underlying_symbol = getattr(item, "underlying_symbol", "")
        if underlying_symbol:
            candidates.append(underlying_symbol)

        for text in candidates:
            if key in self._normalize_underlying_text(text):
                return True

        return False

    def get_index_spot(self,underlying: str,*,use_cache_only: bool = True,) -> FyersIndexSpotSymbol | None:
        symbols = self.load_cache() if use_cache_only else self.fetch_symbol_master()
        for item in symbols:
            if isinstance(item, FyersIndexSpotSymbol) and self._matches_underlying(item, underlying):
                return item
        return None

    def get_futures_for_underlying(self,underlying: str,*,use_cache_only: bool = True,) -> list[FyersFutureSymbol]:
        symbols = self.load_cache() if use_cache_only else self.fetch_symbol_master()
        results = [item for item in symbols if isinstance(item, FyersFutureSymbol) and self._matches_underlying(item, underlying)]
        return sorted(results, key=lambda item: item.expiry_epoch)

    def get_options_for_underlying(self,underlying: str,*,use_cache_only: bool = True,) -> list[FyersOptionSymbol]:
        symbols = self.load_cache() if use_cache_only else self.fetch_symbol_master()
        results = [item for item in symbols if isinstance(item, FyersOptionSymbol) and self._matches_underlying(item, underlying)]
        return sorted(results, key=lambda item: (item.expiry_epoch, item.strike, item.option_type))

    def get_ce_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        options = self.get_options_for_underlying(underlying, use_cache_only=use_cache_only)
        return [item for item in options if item.option_type == "CE"]

    def get_pe_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        options = self.get_options_for_underlying(underlying, use_cache_only=use_cache_only)
        return [item for item in options if item.option_type == "PE"]

    def get_expiry_list(self,underlying: str,*, instrument_kind: str = "option",use_cache_only: bool = True,) -> list[int]:
        if instrument_kind == "future":
            contracts = self.get_futures_for_underlying(underlying, use_cache_only=use_cache_only)
        elif instrument_kind == "option":
            contracts = self.get_options_for_underlying(underlying, use_cache_only=use_cache_only)
        else:
            raise ValueError("instrument_kind must be 'future' or 'option'")
        return sorted({item.expiry_epoch for item in contracts if item.expiry_epoch > 0})

    def get_current_next_far_expiries(self,underlying: str,*,instrument_kind: str = "option",use_cache_only: bool = True,) -> dict[str, int | None]:
        expiries = self.get_expiry_list(underlying, instrument_kind=instrument_kind, use_cache_only=use_cache_only)
        return {"current": expiries[0] if len(expiries) > 0 else None,
                    "next": expiries[1] if len(expiries) > 1 else None,
                    "far": expiries[2] if len(expiries) > 2 else None,}

    def get_futures_by_expiry(self,underlying: str,expiry_epoch: int,*,use_cache_only: bool = True,) -> list[FyersFutureSymbol]:
        futures = self.get_futures_for_underlying(underlying, use_cache_only=use_cache_only)
        return [item for item in futures if item.expiry_epoch == expiry_epoch]

    def get_options_by_expiry(self,underlying: str,expiry_epoch: int,*,use_cache_only: bool = True,) -> list[FyersOptionSymbol]:
        options = self.get_options_for_underlying(underlying, use_cache_only=use_cache_only)
        return [item for item in options if item.expiry_epoch == expiry_epoch]

    def get_ce_options_by_expiry(self,underlying: str,expiry_epoch: int,*,use_cache_only: bool = True,) -> list[FyersOptionSymbol]:
        options = self.get_options_by_expiry(underlying, expiry_epoch, use_cache_only=use_cache_only)
        return [item for item in options if item.option_type == "CE"]

    def get_pe_options_by_expiry(self,underlying: str,expiry_epoch: int,*,use_cache_only: bool = True,) -> list[FyersOptionSymbol]:
        options = self.get_options_by_expiry(underlying, expiry_epoch, use_cache_only=use_cache_only)
        return [item for item in options if item.option_type == "PE"]

    @staticmethod
    def format_expiry(expiry_epoch: int) -> str:
        if expiry_epoch <= 0:
            return ""
        return datetime.fromtimestamp(expiry_epoch).strftime("%Y-%m-%d")

    def get_expiry_date_list(self,underlying: str,*,instrument_kind: str = "option",use_cache_only: bool = True,) -> list[str]:
        expiries = self.get_expiry_list(underlying, instrument_kind=instrument_kind, use_cache_only=use_cache_only)
        return [self.format_expiry(item) for item in expiries]

    def get_current_next_far_expiry_dates(self,underlying: str,*,instrument_kind: str = "option",use_cache_only: bool = True,) -> dict[str, str]:
        expiry_map = self.get_current_next_far_expiries(underlying, instrument_kind=instrument_kind, use_cache_only=use_cache_only)
        return {
            "current": self.format_expiry(expiry_map["current"] or 0),
            "next": self.format_expiry(expiry_map["next"] or 0),
            "far": self.format_expiry(expiry_map["far"] or 0),
        }

    @staticmethod
    def _is_monthly_expiry(expiry_epoch: int, expiries: list[int]) -> bool:
        if expiry_epoch <= 0:
            return False

        expiry_date = datetime.fromtimestamp(expiry_epoch).date()
        same_month_expiries = [
            item for item in expiries
            if datetime.fromtimestamp(item).date().year == expiry_date.year
            and datetime.fromtimestamp(item).date().month == expiry_date.month
        ]
        if not same_month_expiries:
            return False
        return expiry_epoch == max(same_month_expiries)

    def get_weekly_expiries(self,underlying: str,*,instrument_kind: str = "option",use_cache_only: bool = True,) -> list[int]:
        expiries = self.get_expiry_list(underlying, instrument_kind=instrument_kind, use_cache_only=use_cache_only)
        return [item for item in expiries if not self._is_monthly_expiry(item, expiries)]

    def get_monthly_expiries(self,underlying: str,*,instrument_kind: str = "option",use_cache_only: bool = True,) -> list[int]:
        expiries = self.get_expiry_list(underlying, instrument_kind=instrument_kind, use_cache_only=use_cache_only)
        return [item for item in expiries if self._is_monthly_expiry(item, expiries)]

    def get_weekly_expiry_dates(self, underlying: str,*,instrument_kind: str = "option",use_cache_only: bool = True,) -> list[str]:
        expiries = self.get_weekly_expiries(underlying, instrument_kind=instrument_kind, use_cache_only=use_cache_only)
        return [self.format_expiry(item) for item in expiries]

    def get_monthly_expiry_dates(self,underlying: str,*,instrument_kind: str = "option",use_cache_only: bool = True,) -> list[str]:
        expiries = self.get_monthly_expiries(underlying, instrument_kind=instrument_kind, use_cache_only=use_cache_only)
        return [self.format_expiry(item) for item in expiries]

    def get_current_weekly_expiry(self, underlying: str, *, use_cache_only: bool = True) -> int | None:
        weekly = self.get_weekly_expiries(underlying, instrument_kind="option", use_cache_only=use_cache_only)
        return weekly[0] if weekly else None

    def get_next_weekly_expiry(self, underlying: str, *, use_cache_only: bool = True) -> int | None:
        weekly = self.get_weekly_expiries(underlying, instrument_kind="option", use_cache_only=use_cache_only)
        return weekly[1] if len(weekly) > 1 else None

    def get_current_monthly_expiry(self,underlying: str,*,instrument_kind: str = "option",use_cache_only: bool = True,) -> int | None:
        monthly = self.get_monthly_expiries(underlying, instrument_kind=instrument_kind, use_cache_only=use_cache_only)
        return monthly[0] if monthly else None

    def get_next_monthly_expiry(self,underlying: str,*,instrument_kind: str = "option",use_cache_only: bool = True,) -> int | None:
        monthly = self.get_monthly_expiries(underlying, instrument_kind=instrument_kind, use_cache_only=use_cache_only)
        return monthly[1] if len(monthly) > 1 else None

    def get_current_weekly_expiry_date(self, underlying: str, *, use_cache_only: bool = True) -> str:
        expiry = self.get_current_weekly_expiry(underlying, use_cache_only=use_cache_only)
        return self.format_expiry(expiry or 0)

    def get_next_weekly_expiry_date(self, underlying: str, *, use_cache_only: bool = True) -> str:
        expiry = self.get_next_weekly_expiry(underlying, use_cache_only=use_cache_only)
        return self.format_expiry(expiry or 0)

    def get_current_monthly_expiry_date(self,underlying: str,*,instrument_kind: str = "option",use_cache_only: bool = True,) -> str:
        expiry = self.get_current_monthly_expiry(underlying, instrument_kind=instrument_kind, use_cache_only=use_cache_only)
        return self.format_expiry(expiry or 0)

    def get_next_monthly_expiry_date(self,underlying: str,*,instrument_kind: str = "option",use_cache_only: bool = True,) -> str:
        expiry = self.get_next_monthly_expiry(underlying, instrument_kind=instrument_kind, use_cache_only=use_cache_only)
        return self.format_expiry(expiry or 0)

    def get_current_weekly_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        expiry = self.get_current_weekly_expiry(underlying, use_cache_only=use_cache_only)
        if expiry is None:
            return []
        return self.get_options_by_expiry(underlying, expiry, use_cache_only=use_cache_only)

    def get_next_weekly_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        expiry = self.get_next_weekly_expiry(underlying, use_cache_only=use_cache_only)
        if expiry is None:
            return []
        return self.get_options_by_expiry(underlying, expiry, use_cache_only=use_cache_only)

    def get_current_monthly_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        expiry = self.get_current_monthly_expiry(underlying, instrument_kind="option", use_cache_only=use_cache_only)
        if expiry is None:
            return []
        return self.get_options_by_expiry(underlying, expiry, use_cache_only=use_cache_only)

    def get_next_monthly_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        expiry = self.get_next_monthly_expiry(underlying, instrument_kind="option", use_cache_only=use_cache_only)
        if expiry is None:
            return []
        return self.get_options_by_expiry(underlying, expiry, use_cache_only=use_cache_only)

    def get_current_monthly_futures(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersFutureSymbol]:
        expiry = self.get_current_monthly_expiry(underlying, instrument_kind="future", use_cache_only=use_cache_only)
        if expiry is None:
            return []
        return self.get_futures_by_expiry(underlying, expiry, use_cache_only=use_cache_only)

    def get_next_monthly_futures(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersFutureSymbol]:
        expiry = self.get_next_monthly_expiry(underlying, instrument_kind="future", use_cache_only=use_cache_only)
        if expiry is None:
            return []
        return self.get_futures_by_expiry(underlying, expiry, use_cache_only=use_cache_only)

    def get_current_weekly_ce_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        options = self.get_current_weekly_options(underlying, use_cache_only=use_cache_only)
        return [item for item in options if item.option_type == "CE"]

    def get_current_weekly_pe_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        options = self.get_current_weekly_options(underlying, use_cache_only=use_cache_only)
        return [item for item in options if item.option_type == "PE"]

    def get_next_weekly_ce_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        options = self.get_next_weekly_options(underlying, use_cache_only=use_cache_only)
        return [item for item in options if item.option_type == "CE"]

    def get_next_weekly_pe_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        options = self.get_next_weekly_options(underlying, use_cache_only=use_cache_only)
        return [item for item in options if item.option_type == "PE"]

    def get_current_monthly_ce_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        options = self.get_current_monthly_options(underlying, use_cache_only=use_cache_only)
        return [item for item in options if item.option_type == "CE"]

    def get_current_monthly_pe_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        options = self.get_current_monthly_options(underlying, use_cache_only=use_cache_only)
        return [item for item in options if item.option_type == "PE"]

    def get_next_monthly_ce_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        options = self.get_next_monthly_options(underlying, use_cache_only=use_cache_only)
        return [item for item in options if item.option_type == "CE"]

    def get_next_monthly_pe_options(self, underlying: str, *, use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        options = self.get_next_monthly_options(underlying, use_cache_only=use_cache_only)
        return [item for item in options if item.option_type == "PE"]

    @staticmethod
    def _unique_sorted_strikes(options: list[FyersOptionSymbol]) -> list[float]:
        return sorted({item.strike for item in options if item.strike > 0})

    @staticmethod
    def _nearest_strike(strikes: list[float], spot_price: float) -> float | None:
        if not strikes:
            return None
        return min(strikes, key=lambda strike: abs(strike - spot_price))

    def get_atm_strike(self, underlying: str, spot_price: float, *, expiry_epoch: int | None = None, use_cache_only: bool = True) -> float | None:
        if expiry_epoch is not None:
            options = self.get_options_by_expiry(underlying, expiry_epoch, use_cache_only=use_cache_only)
        else:
            options = self.get_options_for_underlying(underlying, use_cache_only=use_cache_only)

        strikes = self._unique_sorted_strikes(options)
        return self._nearest_strike(strikes, spot_price)

    def get_atm_option_pair(self, underlying: str, spot_price: float, *, expiry_epoch: int | None = None, 
                            use_cache_only: bool = True) -> tuple[FyersOptionSymbol | None, FyersOptionSymbol | None]:
        if expiry_epoch is None:
            expiry_epoch = self.get_current_weekly_expiry(underlying, use_cache_only=use_cache_only)
        if expiry_epoch is None:
            return None, None

        atm_strike = self.get_atm_strike(underlying, spot_price, expiry_epoch=expiry_epoch, use_cache_only=use_cache_only)
        if atm_strike is None:
            return None, None

        ce_options = self.get_ce_options_by_expiry(underlying, expiry_epoch, use_cache_only=use_cache_only)
        pe_options = self.get_pe_options_by_expiry(underlying, expiry_epoch, use_cache_only=use_cache_only)

        atm_ce = next((item for item in ce_options if item.strike == atm_strike), None)
        atm_pe = next((item for item in pe_options if item.strike == atm_strike), None)

        return atm_ce, atm_pe

    def get_otm_ce_options(self, underlying: str, spot_price: float, *,
                           expiry_epoch: int | None = None,count: int = 5,use_cache_only: bool = True) -> list[FyersOptionSymbol]:
        if expiry_epoch is None:
            expiry_epoch = self.get_current_weekly_expiry(underlying, use_cache_only=use_cache_only)
        if expiry_epoch is None:
            return []

        atm_strike = self.get_atm_strike(underlying, spot_price, expiry_epoch=expiry_epoch, use_cache_only=use_cache_only)
        if atm_strike is None:
            return []

        ce_options = self.get_ce_options_by_expiry(underlying, expiry_epoch, use_cache_only=use_cache_only)
        results = [item for item in ce_options if item.strike > atm_strike]
        return results[:count]

    def get_otm_pe_options(self,underlying: str,spot_price: float,*,
                           expiry_epoch: int | None = None,count: int = 5,use_cache_only: bool = True,) -> list[FyersOptionSymbol]:
        if expiry_epoch is None:
            expiry_epoch = self.get_current_weekly_expiry(underlying, use_cache_only=use_cache_only)
        if expiry_epoch is None:
            return []

        atm_strike = self.get_atm_strike(underlying, spot_price, expiry_epoch=expiry_epoch, use_cache_only=use_cache_only)
        if atm_strike is None:
            return []

        pe_options = self.get_pe_options_by_expiry(underlying, expiry_epoch, use_cache_only=use_cache_only)
        results = [item for item in pe_options if item.strike < atm_strike]
        results.sort(key=lambda item: item.strike, reverse=True)
        return results[:count]

    def get_itm_ce_options(self,underlying: str,spot_price: float,*,
                           expiry_epoch: int | None = None,count: int = 5,use_cache_only: bool = True,) -> list[FyersOptionSymbol]:
        if expiry_epoch is None:
            expiry_epoch = self.get_current_weekly_expiry(underlying, use_cache_only=use_cache_only)
        if expiry_epoch is None:
            return []

        atm_strike = self.get_atm_strike(underlying, spot_price, expiry_epoch=expiry_epoch, use_cache_only=use_cache_only)
        if atm_strike is None:
            return []

        ce_options = self.get_ce_options_by_expiry(underlying, expiry_epoch, use_cache_only=use_cache_only)
        results = [item for item in ce_options if item.strike < atm_strike]
        results.sort(key=lambda item: item.strike, reverse=True)
        return results[:count]

    def get_itm_pe_options(self,underlying: str,spot_price: float,*,expiry_epoch: int | None = None,count: int = 5,
                           use_cache_only: bool = True,) -> list[FyersOptionSymbol]:
        if expiry_epoch is None:
            expiry_epoch = self.get_current_weekly_expiry(underlying, use_cache_only=use_cache_only)
        if expiry_epoch is None:
            return []

        atm_strike = self.get_atm_strike(underlying, spot_price, expiry_epoch=expiry_epoch, use_cache_only=use_cache_only)
        if atm_strike is None:
            return []

        pe_options = self.get_pe_options_by_expiry(underlying, expiry_epoch, use_cache_only=use_cache_only)
        results = [item for item in pe_options if item.strike > atm_strike]
        return results[:count]


if __name__ == "__main__":
    service = FyersSymbolService()

    try:
        print(f"Cache file: {service.cache_path}")
        all_symbols = service.ensure_daily_cache(exchanges=["NSE_CM", "BSE_CM", "NSE_FO", "BSE_FO"], force_refresh=False)
        print(f"Total cached symbols: {len(all_symbols)}")

        print("\nSearch: SENSEX spot")
        sensex_spot = service.get_index_spot("SENSEX", use_cache_only=True)
        if sensex_spot is None:
            print("No SENSEX spot found")
        else:
            print(f"{sensex_spot.kind} | {sensex_spot.symbol} | {sensex_spot.display_name} | {sensex_spot.exchange_code} | {sensex_spot.segment_code} | {sensex_spot.token}")

        print("\nCurrent weekly expiry: SENSEX")
        print(service.get_current_weekly_expiry_date("SENSEX", use_cache_only=True))

        print("\nNext weekly expiry: SENSEX")
        print(service.get_next_weekly_expiry_date("SENSEX", use_cache_only=True))

        print("\nCurrent monthly option expiry: SENSEX")
        print(service.get_current_monthly_expiry_date("SENSEX", instrument_kind="option", use_cache_only=True))

        print("\nCurrent monthly future expiry: SENSEX")
        print(service.get_current_monthly_expiry_date("SENSEX", instrument_kind="future", use_cache_only=True))

        print("\nCurrent weekly CE count: SENSEX")
        current_weekly_ce = service.get_current_weekly_ce_options("SENSEX", use_cache_only=True)
        print(len(current_weekly_ce))
        for item in current_weekly_ce[:5]:
            print(f"CE | {item.symbol} | {item.display_name} | expiry={service.format_expiry(item.expiry_epoch)} | strike={item.strike}")

        print("\nCurrent weekly PE count: SENSEX")
        current_weekly_pe = service.get_current_weekly_pe_options("SENSEX", use_cache_only=True)
        print(len(current_weekly_pe))
        for item in current_weekly_pe[:5]:
            print(f"PE | {item.symbol} | {item.display_name} | expiry={service.format_expiry(item.expiry_epoch)} | strike={item.strike}")

        print("\nCurrent monthly CE count: SENSEX")
        current_monthly_ce = service.get_current_monthly_ce_options("SENSEX", use_cache_only=True)
        print(len(current_monthly_ce))
        for item in current_monthly_ce[:5]:
            print(f"CE | {item.symbol} | {item.display_name} | expiry={service.format_expiry(item.expiry_epoch)} | strike={item.strike}")

        print("\nCurrent monthly PE count: SENSEX")
        current_monthly_pe = service.get_current_monthly_pe_options("SENSEX", use_cache_only=True)
        print(len(current_monthly_pe))
        for item in current_monthly_pe[:5]:
            print(f"PE | {item.symbol} | {item.display_name} | expiry={service.format_expiry(item.expiry_epoch)} | strike={item.strike}")

        print("\nCurrent monthly futures: SENSEX")
        current_monthly_futures = service.get_current_monthly_futures("SENSEX", use_cache_only=True)
        for item in current_monthly_futures:
            print(f"{item.kind} | {item.symbol} | {item.display_name} | expiry={service.format_expiry(item.expiry_epoch)}")

        sensex_spot_price = 65050.0

        print("\nATM strike: SENSEX")
        atm_strike = service.get_atm_strike("SENSEX", sensex_spot_price, use_cache_only=True)
        print(atm_strike)

        print("\nATM CE / PE: SENSEX")
        atm_ce, atm_pe = service.get_atm_option_pair("SENSEX", sensex_spot_price, use_cache_only=True)
        if atm_ce:
            print(f"ATM CE | {atm_ce.symbol} | {atm_ce.display_name} | expiry={service.format_expiry(atm_ce.expiry_epoch)} | strike={atm_ce.strike}")
        if atm_pe:
            print(f"ATM PE | {atm_pe.symbol} | {atm_pe.display_name} | expiry={service.format_expiry(atm_pe.expiry_epoch)} | strike={atm_pe.strike}")

        print("\nOTM CE: SENSEX")
        for item in service.get_otm_ce_options("SENSEX", sensex_spot_price, count=5, use_cache_only=True):
            print(f"OTM CE | {item.symbol} | {item.display_name} | expiry={service.format_expiry(item.expiry_epoch)} | strike={item.strike}")

        print("\nOTM PE: SENSEX")
        for item in service.get_otm_pe_options("SENSEX", sensex_spot_price, count=5, use_cache_only=True):
            print(f"OTM PE | {item.symbol} | {item.display_name} | expiry={service.format_expiry(item.expiry_epoch)} | strike={item.strike}")

        print("\nITM CE: SENSEX")
        for item in service.get_itm_ce_options("SENSEX", sensex_spot_price, count=5, use_cache_only=True):
            print(f"ITM CE | {item.symbol} | {item.display_name} | expiry={service.format_expiry(item.expiry_epoch)} | strike={item.strike}")

        print("\nITM PE: SENSEX")
        for item in service.get_itm_pe_options("SENSEX", sensex_spot_price, count=5, use_cache_only=True):
            print(f"ITM PE | {item.symbol} | {item.display_name} | expiry={service.format_expiry(item.expiry_epoch)} | strike={item.strike}")

    except requests.RequestException as exc:
        print(f"Network/API error: {exc}")
    except Exception as exc:
        print(f"Unexpected error: {exc}")

# python -m trading_app.broker.symbols