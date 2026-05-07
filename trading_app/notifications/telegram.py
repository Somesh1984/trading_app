from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import aiohttp

MAX_MESSAGE_LENGTH = 3900


@dataclass(slots=True)
class TelegramNotifier:
    bot_token: str | None = None
    chat_id: str | None = None
    timeout: int = 5

    def __post_init__(self) -> None:
        self.bot_token = self.bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = self.chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

        if not self.bot_token:
            raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

        if not self.chat_id:
            raise RuntimeError("Missing TELEGRAM_CHAT_ID")

    async def send_text(self, text: str) -> bool:
        if not text.strip():
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        timeout = aiohttp.ClientTimeout(total=self.timeout)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    json={
                        "chat_id": self.chat_id,
                        "text": text[:MAX_MESSAGE_LENGTH],
                        "disable_web_page_preview": True,
                    },
                ) as response:
                    if response.status >= 400:
                        return False

                    data = await response.json()

            return bool(data.get("ok"))

        except (asyncio.TimeoutError, aiohttp.ClientError):
            return False

    async def send_lines(self, title: str, lines: list[str]) -> bool:
        if not lines:
            return False

        ok = True
        chunk: list[str] = []
        current_len = len(title) + 2

        for line in lines:
            line_len = len(line) + 1

            if chunk and current_len + line_len > MAX_MESSAGE_LENGTH:
                sent = await self.send_text(title + "\n\n" + "\n".join(chunk))
                ok = sent and ok
                chunk = []
                current_len = len(title) + 2

            chunk.append(line)
            current_len += line_len

        if chunk:
            sent = await self.send_text(title + "\n\n" + "\n".join(chunk))
            ok = sent and ok

        return ok