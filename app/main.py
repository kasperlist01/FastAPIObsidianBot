import asyncio
from api import start_api
from bot import start_bot
from database import init_db


async def main():
    await asyncio.gather(
        init_db(),
        asyncio.to_thread(start_api),
        start_bot()
    )

if __name__ == "__main__":
    asyncio.run(main())
