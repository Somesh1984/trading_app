
from __future__ import annotations

import base64
import time
from threading import Lock
from urllib.parse import parse_qs, urlparse

import pyotp
import requests
from fyers_apiv3 import fyersModel

from ..settings import (
    FYERS_CLIENT_ID,
    FYERS_PIN,
    FYERS_REDIRECT_URI,
    FYERS_SECRET_KEY,
    FYERS_TOTP_KEY,
    FYERS_USER_ID,
)


_AUTH_LOCK = Lock()
_CACHED_ACCESS_TOKEN: str | None = None
_LAST_AUTH_FAILURE: tuple[float, "FyersAuthError"] | None = None
AUTH_FAILURE_COOLDOWN_SECONDS = 1


class FyersAuthError(RuntimeError):
    """Raised when FYERS authentication cannot complete."""


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("ascii")).decode("ascii")


def _request_auth_post(
    url: str,
    *,
    session: requests.Session | None = None,
    **kwargs,
) -> requests.Response:
    client = session or requests

    try:
        response = client.post(url, timeout=30, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as exc:
        raise FyersAuthError(
            f"FYERS auth request failed for {url}: {exc}"
        ) from exc


def _generate_new_access_token() -> str:
    send_otp_url = "https://api-t2.fyers.in/vagator/v2/send_login_otp_v2"
    verify_otp_url = "https://api-t2.fyers.in/vagator/v2/verify_otp"
    verify_pin_url = "https://api-t2.fyers.in/vagator/v2/verify_pin_v2"
    token_url = "https://api-t1.fyers.in/api/v3/token"

    otp_resp = _request_auth_post(
        send_otp_url,
        json={"fy_id": _b64(FYERS_USER_ID), "app_id": "2"},
    )
    otp_data = otp_resp.json()
    request_key = otp_data["request_key"]

    otp_code = pyotp.TOTP(FYERS_TOTP_KEY).now()
    otp_verify_resp = _request_auth_post(
        verify_otp_url,
        json={"request_key": request_key, "otp": otp_code},
    )
    otp_verify_data = otp_verify_resp.json()
    pin_request_key = otp_verify_data["request_key"]

    session = requests.Session()
    pin_resp = _request_auth_post(
        verify_pin_url,
        session=session,
        json={
            "request_key": pin_request_key,
            "identity_type": "pin",
            "identifier": _b64(FYERS_PIN),
        },
    )
    pin_data = pin_resp.json()

    bearer_token = pin_data["data"]["access_token"]
    session.headers.update({"authorization": f"Bearer {bearer_token}"})

    token_resp = _request_auth_post(
        token_url,
        session=session,
        json={
            "fyers_id": FYERS_USER_ID,
            "app_id": FYERS_CLIENT_ID[:-4],
            "redirect_uri": FYERS_REDIRECT_URI,
            "appType": "100",
            "code_challenge": "",
            "state": "None",
            "scope": "",
            "nonce": "",
            "response_type": "code",
            "create_cookie": True,
        },
    )
    token_data = token_resp.json()

    auth_code_url = token_data["Url"]
    auth_code = parse_qs(urlparse(auth_code_url).query)["auth_code"][0]

    app_session = fyersModel.SessionModel(
        client_id=FYERS_CLIENT_ID,
        secret_key=FYERS_SECRET_KEY,
        redirect_uri=FYERS_REDIRECT_URI,
        response_type="code",
        grant_type="authorization_code",
    )
    app_session.set_token(auth_code)

    final_token = app_session.generate_token()
    return final_token["access_token"]


def generate_access_token(*, force_refresh: bool = False) -> str:
    global _CACHED_ACCESS_TOKEN, _LAST_AUTH_FAILURE

    with _AUTH_LOCK:
        if _CACHED_ACCESS_TOKEN is None or force_refresh:
            if _LAST_AUTH_FAILURE is not None:
                failed_at, failure = _LAST_AUTH_FAILURE
                if time.monotonic() - failed_at < AUTH_FAILURE_COOLDOWN_SECONDS:
                    raise failure

            try:
                _CACHED_ACCESS_TOKEN = _generate_new_access_token()
                _LAST_AUTH_FAILURE = None
            except FyersAuthError as exc:
                _LAST_AUTH_FAILURE = (time.monotonic(), exc)
                raise

        return _CACHED_ACCESS_TOKEN


def clear_cached_access_token() -> None:
    global _CACHED_ACCESS_TOKEN
    with _AUTH_LOCK:
        _CACHED_ACCESS_TOKEN = None


def login() -> fyersModel.FyersModel:
    access_token = generate_access_token()
    return fyersModel.FyersModel(
        client_id=FYERS_CLIENT_ID,
        token=access_token,
        is_async=False,
        log_path="",
    )

