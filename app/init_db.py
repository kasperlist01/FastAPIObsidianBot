import asyncio
from database import init_db

async def main():
    print("🚀 Инициализация базы данных...")
    await init_db()
    print("✅ База данных готова!")

if __name__ == "__main__":
    asyncio.run(main())
