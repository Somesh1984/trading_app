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

    # def place_order(
    #     self,
    #     *,
    #     symbol: str,
    #     qty: int,
    #     side: int,
    #     productType: str = "INTRADAY",
    #     orderType: int = 2,
    #     limitPrice: float = 0,
    #     stopPrice: float = 0,
    #     validity: str = "DAY",
    #     disclosedQty: int = 0,
    #     offlineOrder: bool = False,
    #     stopLoss: float = 0,
    #     takeProfit: float = 0,
    # ) -> dict[str, Any]:
    #     payload = {
    #         "symbol": symbol,
    #         "qty": qty,
    #         "type": orderType,
    #         "side": side,
    #         "productType": productType,
    #         "limitPrice": limitPrice,
    #         "stopPrice": stopPrice,
    #         "validity": validity,
    #         "disclosedQty": disclosedQty,
    #         "offlineOrder": offlineOrder,
    #         "stopLoss": stopLoss,
    #         "takeProfit": takeProfit,
    #     }

    #     response = self.get_client().place_order(payload)
    #     if not isinstance(response, dict):
    #         raise RuntimeError("Invalid place_order response from FYERS.")
    #     return response

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





# if __name__ == "__main__":
#     broker = Broker()
#     print("Broker created")
#     profile = broker.get_profile()
#     print(profile)