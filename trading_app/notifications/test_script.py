from trading_app.logger import get_logger, log_debug, log_error, log_info, log_warning

logger = get_logger(__name__)

import asyncio

from trading_app.notifications.telegram import TelegramNotifier


async def main() -> None:
    notifier = TelegramNotifier()

    result = await notifier.send_text(
        "Jai Bala Ji Maharaj\n"
        "ASYNC TEST MESSAGE FROM FYERS SYSTEM\n"
        "Market Closed"
    )

    log_info(logger, "SENT:", result)


if __name__ == "__main__":
    asyncio.run(main())