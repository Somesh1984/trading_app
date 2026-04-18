


from __future__ import annotations

import base64
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


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("ascii")).decode("ascii")


def generate_access_token() -> str:
    send_otp_url = "https://api-t2.fyers.in/vagator/v2/send_login_otp_v2"
    verify_otp_url = "https://api-t2.fyers.in/vagator/v2/verify_otp"
    verify_pin_url = "https://api-t2.fyers.in/vagator/v2/verify_pin_v2"
    token_url = "https://api-t1.fyers.in/api/v3/token"

    otp_resp = requests.post(
        send_otp_url,
        json={"fy_id": _b64(FYERS_USER_ID), "app_id": "2"},
        timeout=30,
    )
    otp_resp.raise_for_status()
    otp_data = otp_resp.json()
    request_key = otp_data["request_key"]

    otp_code = pyotp.TOTP(FYERS_TOTP_KEY).now()
    otp_verify_resp = requests.post(
        verify_otp_url,
        json={"request_key": request_key, "otp": otp_code},
        timeout=30,
    )
    otp_verify_resp.raise_for_status()
    otp_verify_data = otp_verify_resp.json()
    pin_request_key = otp_verify_data["request_key"]

    session = requests.Session()
    pin_resp = session.post(
        verify_pin_url,
        json={
            "request_key": pin_request_key,
            "identity_type": "pin",
            "identifier": _b64(FYERS_PIN),
        },
        timeout=30,
    )
    pin_resp.raise_for_status()
    pin_data = pin_resp.json()

    bearer_token = pin_data["data"]["access_token"]
    session.headers.update({"authorization": f"Bearer {bearer_token}"})

    token_resp = session.post(
        token_url,
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
        timeout=30,
    )
    token_resp.raise_for_status()
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
    access_token = final_token["access_token"]
    return access_token


def login() -> fyersModel.FyersModel:
    access_token = generate_access_token()
    return fyersModel.FyersModel(
        client_id=FYERS_CLIENT_ID,
        token=access_token,
        is_async=False,
        log_path="",
    )