import asyncio
from sqlalchemy import text
from app.db.session import engine


async def main():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        print("Підключення працює:", result.scalar())
    await engine.dispose()


asyncio.run(main())