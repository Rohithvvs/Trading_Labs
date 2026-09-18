import asyncio
from app.db.session import SessionLocal

async def main():
    db = SessionLocal()
    
    from sqlalchemy import text
    res = await db.execute(text("SELECT DISTINCT symbol FROM ohlcv_daily WHERE symbol LIKE '%NIFTY%'"))
    symbols = res.fetchall()
    print("Symbols matching NIFTY:", symbols)
    
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
