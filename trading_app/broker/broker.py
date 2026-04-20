from __future__ import annotations

from datetime import date
from typing import Any

from fyers_apiv3 import fyersModel

from .auth import login
from ..settings import validate_settings


class Broker:
    def __init__(self, *, auto_login: bool = True) -> None:
        self._auto_login = auto_login
        self._client: fyersModel.FyersModel | None = None

    def get_client(self) -> fyersModel.FyersModel:
        if self._client is None:
            if not self._auto_login:
                raise RuntimeError(
                    "FYERS client is not authenticated and auto_login is disabled."
                )
            validate_settings()
            self._client = login()
        return self._client

    def refresh_login(self) -> fyersModel.FyersModel:
        validate_settings()
        self._client = login()
        return self._client

    def get_profile(self) -> dict[str, Any]:
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
    ) -> list[list[Any]]:
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
            return []

        candles = response.get("candles", [])
        return candles if isinstance(candles, list) else []


    def get_orderbook(self) -> dict[str, Any]:
        response = self.get_client().orderbook()
        if not isinstance(response, dict):
            raise RuntimeError("Invalid orderbook response from FYERS.")
        return response



    def cancel_order(self, order_id: str) -> dict[str, Any]:
        payload = {"id": order_id}
        response = self.get_client().cancel_order(payload)
        if not isinstance(response, dict):
            raise RuntimeError("Invalid cancel_order response from FYERS.")
        return response



    def get_positions(self) -> dict[str, Any]:
        response = self.get_client().positions()
        if not isinstance(response, dict):
            raise RuntimeError("Invalid positions response from FYERS.")
        return response


    def get_holdings(self) -> dict[str, Any]:
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

    def get_history_for_symbols(self,*,symbols: list[str],resolution: str,date_from: str,date_to: str,cont_flag: str = "1",) -> dict[str, dict]:
        results: dict[str, dict] = {}

        for symbol in symbols:
            results[symbol] = self.get_history(
                                            symbol=symbol,
                                            resolution=resolution,
                                            date_from=date_from,
                                            date_to=date_to,
                                            cont_flag=cont_flag,
                                            )

        return results


    def get_quotes(self,*,symbols: list[str]) -> dict:
        client = self.get_client()

        data = {
            "symbols": ",".join(symbols)
        }

        return client.quotes(data=data)


    def get_depth(self,*,symbols: list[str],ohlcv_flag: int = 1) -> dict:
        client = self.get_client()

        data = {
            "symbol": ",".join(symbols),
            "ohlcv_flag": str(ohlcv_flag),
        }

        return client.depth(data=data)



    def get_index_spot_prices(self) -> dict[str, dict[str, float]]:
        symbols = [
                    "NSE:NIFTY50-INDEX",
                    "BSE:SENSEX-INDEX",]

        response = self.get_quotes(symbols=symbols)

        result: dict[str, dict[str, float]] = {}

        data = response.get("d", [])

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
                            "current": current_price,}

        return result






if __name__ == "__main__":
    broker = Broker()

    prices = broker.get_index_spot_prices()
    print("\n=== INDEX SPOT PRICES ===")
    print(prices)

    # python -m trading_app.broker.broker