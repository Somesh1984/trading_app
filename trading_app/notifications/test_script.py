import asyncio

from trading_app.notifications.telegram import TelegramNotifier


async def main() -> None:
    notifier = TelegramNotifier()

    result = await notifier.send_text(
        "Jai Bala Ji Maharaj\n"
        "ASYNC TEST MESSAGE FROM FYERS SYSTEM\n"
        "Market Closed"
    )

    print("SENT:", result)


if __name__ == "__main__":
    asyncio.run(main())