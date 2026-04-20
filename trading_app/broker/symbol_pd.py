
from __future__ import annotations

from io import StringIO

import pandas as pd
import requests
import math


class FyersSymbolService:
    SYMBOL_MASTER_URLS: dict[str, str] = {
                                            "NSE_CM": "https://public.fyers.in/sym_details/NSE_CM.csv",
                                            "BSE_CM": "https://public.fyers.in/sym_details/BSE_CM.csv",
                                            "NSE_FO": "https://public.fyers.in/sym_details/NSE_FO.csv",
                                            "BSE_FO": "https://public.fyers.in/sym_details/BSE_FO.csv",
                                                                                                        }
    
    INDEX_CONFIG: dict[str, dict[str, str | int]] = {
                                                        "NIFTY": {
                                                                    "spot_symbol": "NSE:NIFTY50-INDEX",
                                                                    "fo_exchange": "NSE_FO",
                                                                    "underlying_symbol": "NIFTY",
                                                                    "strike_step": 50,},
                                                        "SENSEX": {
                                                                    "spot_symbol": "BSE:SENSEX-INDEX",
                                                                    "fo_exchange": "BSE_FO",
                                                                    "underlying_symbol": "SENSEX",
                                                                    "strike_step": 100,},}

    def fetch_symbol_master_df(self,exchanges: list[str] | None = None,*,timeout: int = 60,) -> pd.DataFrame:
        selected_exchanges = exchanges or list(self.SYMBOL_MASTER_URLS.keys())
        frames: list[pd.DataFrame] = []

        for exchange_key in selected_exchanges:
            url = self.SYMBOL_MASTER_URLS.get(exchange_key)
            if not url:
                raise ValueError(f"Unsupported exchange key: {exchange_key}")

            response = requests.get(url, timeout=timeout)
            response.raise_for_status()

            df = pd.read_csv(StringIO(response.text), header=None)
            df["source_file"] = exchange_key
            frames.append(df)

        if not frames:
            return pd.DataFrame()

        df = pd.concat(frames, ignore_index=True)

        df.columns = ["Symbol Details","Name","Exchange Instrument Type","Minimum Lot Size","Tick Size","ISIN","Trading Session",
                      "Last Update Date","Expiry Date","Symbol Ticker","Exchange","Segment","Scrip Code","Underlying Symbol",
                      "Underlying Scrip Code","Strike Price","Option Type","Underlying FyToken","Reserved Column 1","Reserved Column 2",
                      "Reserved Column 3","Source File", ]

        return df
    
    def get_spot_index_symbols(self) -> list[str]:
        return ["NSE:NIFTY50-INDEX","BSE:SENSEX-INDEX",]
    

    def _parse_expiry_epoch(self,expiry_series: pd.Series,) -> pd.Series:
        numeric_expiry = pd.to_numeric(expiry_series, errors="coerce")

        if numeric_expiry.dropna().empty:
            return pd.to_datetime(numeric_expiry, errors="coerce")

        max_value = numeric_expiry.dropna().max()

        if max_value > 9999999999:
            return pd.to_datetime(numeric_expiry, unit="ms", errors="coerce")

        return pd.to_datetime(numeric_expiry, unit="s", errors="coerce")




    def get_open_based_strike_range(self,*,day_open_price: float,current_spot_price: float,strike_step: int,base_count: int = 5,) -> list[int]:

        open_strike = math.floor(day_open_price / strike_step) * strike_step
        current_strike = math.floor(current_spot_price / strike_step) * strike_step

        lower_strike = open_strike - (base_count * strike_step)
        upper_strike = open_strike + (base_count * strike_step)

        # ensure current covered
        lower_strike = min(lower_strike, current_strike)
        upper_strike = max(upper_strike, current_strike)

        return list(range(lower_strike, upper_strike + strike_step, strike_step))
    
    def get_option_symbols_for_strikes(self,df: pd.DataFrame,*,underlying: str,strikes: list[int],expiry_epoch: int | None = None,) -> list[str]:
            if df.empty or not strikes:
                return []

            working_df = df.copy()

            working_df["Underlying Symbol"] = (working_df["Underlying Symbol"].astype(str).str.strip().str.upper())
            working_df["Option Type"] = (working_df["Option Type"].astype(str).str.strip().str.upper())
            working_df["Symbol Ticker"] = (working_df["Symbol Ticker"].astype(str).str.strip())
            working_df["Strike Price"] = pd.to_numeric(working_df["Strike Price"],errors="coerce",)
            working_df["Expiry Date"] = pd.to_numeric(working_df["Expiry Date"],errors="coerce")

            option_df = working_df[(working_df["Underlying Symbol"].eq(underlying.strip().upper()))
                                   & working_df["Option Type"].isin(["CE", "PE"])
                                   & working_df["Strike Price"].isin(strikes)]

            if expiry_epoch is not None:
                option_df = option_df[option_df["Expiry Date"].eq(expiry_epoch)]

            option_df = option_df.sort_values(by=["Strike Price", "Option Type"],ascending=[True, True],)

            return option_df["Symbol Ticker"].dropna().tolist()

    # def get_nearest_expiry_date(self,df: pd.DataFrame,*,underlying: str,) -> pd.Timestamp | None:

    #         if df.empty:
    #             return None

    #         working_df = df.copy()

    #         working_df["Underlying Symbol"] = (working_df["Underlying Symbol"].astype(str).str.strip().str.upper())
    #         working_df["Option Type"] = (working_df["Option Type"].astype(str).str.strip().str.upper())
    #         working_df["Expiry Date"] = (working_df["Expiry Date"].astype(str).str.strip())

    #         option_df = working_df[(working_df["Underlying Symbol"].eq(underlying.strip().upper()))
    #                                 & working_df["Option Type"].isin(["CE","PE"])
    #                                 & working_df["Expiry Date"].ne("")]

    #         if option_df.empty:
    #             return None

    #         option_df = option_df.copy()
    #         option_df["Expiry Parsed"] = pd.to_datetime(option_df["Expiry Date"],errors="coerce",dayfirst=True)

    #         option_df = option_df.dropna(subset=["Expiry Parsed"])

    #         if option_df.empty:
    #             return None

    #         return option_df["Expiry Parsed"].min().normalize()


    def get_nearest_expiry_epoch(self,df: pd.DataFrame,*,underlying: str,) -> int | None:

        if df.empty:
            return None

        working_df = df.copy()

        working_df["Underlying Symbol"] = (working_df["Underlying Symbol"].astype(str).str.strip().str.upper())
        working_df["Option Type"] = (working_df["Option Type"].astype(str).str.strip().str.upper())
        working_df["Expiry Date"] = pd.to_numeric(working_df["Expiry Date"],errors="coerce")

        option_df = working_df[(working_df["Underlying Symbol"].eq(underlying.strip().upper()))
                               & working_df["Option Type"].isin(["CE","PE"])]

        option_df = option_df.dropna(subset=["Expiry Date"])

        if option_df.empty:
            return None

        option_df = option_df.copy()
        option_df["Expiry Parsed"] = self._parse_expiry_epoch(option_df["Expiry Date"])

        option_df = option_df.dropna(subset=["Expiry Parsed"])

        if option_df.empty:
            return None

        today = pd.Timestamp.now().normalize()
        future_df = option_df[option_df["Expiry Parsed"].dt.normalize().ge(today)]

        if not future_df.empty:
            nearest_row = future_df.sort_values(by=["Expiry Parsed", "Expiry Date"]).iloc[0]
            return int(nearest_row["Expiry Date"])

        nearest_row = option_df.sort_values(by=["Expiry Parsed", "Expiry Date"]).iloc[0]
        return int(nearest_row["Expiry Date"])



    def build_option_symbols_from_prices(self,*,index_name: str,day_open_price: float,current_spot_price: float,base_count: int = 5,) -> list[str]:

        config = self.INDEX_CONFIG.get(index_name.strip().upper())

        if config is None:
            return []

        fo_exchange = str(config["fo_exchange"])
        underlying_symbol = str(config["underlying_symbol"])
        strike_step = int(config["strike_step"])

        df = self.fetch_symbol_master_df(exchanges=[fo_exchange])

        strikes = self.get_open_based_strike_range(
            day_open_price=day_open_price,
            current_spot_price=current_spot_price,
            strike_step=strike_step,
            base_count=base_count,
        )



        expiry_epoch = self.get_nearest_expiry_epoch(
            df,
            underlying=underlying_symbol,
        )

        return self.get_option_symbols_for_strikes(
            df,
            underlying=underlying_symbol,
            strikes=strikes,
            expiry_epoch=expiry_epoch,
        )




    def build_subscription_symbols(self,*,index_prices: dict[str, dict[str, float]],include_spot: bool = True,base_count: int = 5,) -> list[str]:

        symbols: list[str] = []

        for index_name, price_data in index_prices.items():

            config = self.INDEX_CONFIG.get(index_name.strip().upper())
            if config is None:
                continue

            if include_spot:
                symbols.append(str(config["spot_symbol"]))

            day_open_price = float(price_data["open"])
            current_spot_price = float(price_data["current"])

            option_symbols = self.build_option_symbols_from_prices(
                index_name=index_name,
                day_open_price=day_open_price,
                current_spot_price=current_spot_price,
                base_count=base_count,
            )

            symbols.extend(option_symbols)

        return list(dict.fromkeys(symbols))







# if __name__ == "__main__":
#     service = FyersSymbolService()

#     strikes = service.get_open_based_strike_range(
#         day_open_price=24235,
#         current_spot_price=24540,
#         strike_step=50,
#         base_count=5,
#     )
#     print(strikes)


if __name__ == "__main__":
    service = FyersSymbolService()

    symbols = service.build_subscription_symbols(
        index_prices={
            "NIFTY": {"open": 24235.0, "current": 24540.0},
            "SENSEX": {"open": 79850.0, "current": 80120.0},
        },
        include_spot=True,
        base_count=5,
    )

    for symbol in symbols[:40]:
        print(symbol)




# python -m trading_app.broker.symbol_pd
