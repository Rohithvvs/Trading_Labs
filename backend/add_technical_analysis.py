import asyncio
from app.db.session import engine
from sqlalchemy import text

async def main():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE recommendation_engine_decisions ADD COLUMN IF NOT EXISTS technical_analysis JSONB;"))
            print("Successfully added technical_analysis column.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
