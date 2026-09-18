import asyncio
import pandas as pd
from app.db.session import SessionLocal
from app.services.market_data_service import MarketDataService

async def main():
    db = SessionLocal()
    svc = MarketDataService(db)
    
    symbols_to_try = ["NIFTY 500", "^CRSMA", "^NSEI", "NIFTY500"]
    for sym in symbols_to_try:
        try:
            df = await svc.load_full_history(sym, "1D")
            print(f"Symbol {sym}: df size {len(df)}")
            if not df.empty:
                print(df.head())
        except Exception as e:
            print(f"Symbol {sym} error: {e}")
            
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
