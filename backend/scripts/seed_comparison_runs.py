"""Seed comparison runs and candidate stocks for Strategy Comparison & Venn Diagram."""

import datetime
import uuid
from app.db.session import SessionLocal
from app.models.auth import User
from app.models.indicator_scanner import IndicatorDefinition, IndicatorScanResult, IndicatorScanRun


def seed_comparison_runs():
    db = SessionLocal()
    try:
        user = db.query(User).first()
        now = datetime.datetime.now(datetime.timezone.utc)

        # 1. Ensure 15d8bf22-4683-4d1e-bd92-db14a273373d exists
        def1_id = uuid.UUID("15d8bf22-4683-4d1e-bd92-db14a273373d")
        d1 = db.query(IndicatorDefinition).filter(IndicatorDefinition.id == def1_id).first()
        if not d1:
            d1 = IndicatorDefinition(
                id=def1_id,
                user_id=user.id,
                name="Top 5: Minervini Stage-2 VCP [SCAN]",
                description="Stage-2 Trend Template + 20d/126d VCP Contraction (<=40%) + 15d Pivot Breakout.",
                source_code='//@version=6\nindicator("Top 5: Minervini Stage-2 VCP")\nplot(close)',
                script_version=6,
                language_mode="pine_v6",
                timeframe="1D",
                parsed_definition={
                    "entry_conditions": [
                        "Close > SMA50",
                        "SMA50 > SMA150",
                        "SMA150 > SMA200",
                        "VCP Contraction <= 40%",
                        "15d Pivot Breakout",
                    ]
                },
                validation_status="valid",
                validation_errors=[],
                required_bars=252,
                created_at=now,
                updated_at=now,
            )
            db.add(d1)
            db.commit()
            print("Created d1:", d1.id, d1.name)

        # 2. Ensure 321b5ca5-6276-4718-ac3c-c23a3122ca60 exists
        def2_id = uuid.UUID("321b5ca5-6276-4718-ac3c-c23a3122ca60")
        d2 = db.query(IndicatorDefinition).filter(IndicatorDefinition.id == def2_id).first()
        if not d2:
            d2 = IndicatorDefinition(
                id=def2_id,
                user_id=user.id,
                name="Top 1: App Preset Momentum [SCAN]",
                description="Close > SMA50 > SMA200, RSI > 55, Volume > SMA20.",
                source_code='//@version=6\nindicator("Top 1: App Preset Momentum")\nplot(close)',
                script_version=6,
                language_mode="pine_v6",
                timeframe="1D",
                parsed_definition={
                    "entry_conditions": [
                        "Close > SMA50",
                        "SMA50 > SMA200",
                        "RSI(14) > 55",
                        "Volume > SMA(Volume, 20)",
                    ]
                },
                validation_status="valid",
                validation_errors=[],
                required_bars=200,
                created_at=now,
                updated_at=now,
            )
            db.add(d2)
            db.commit()
            print("Created d2:", d2.id, d2.name)

        # 3. Candidate stock pools
        consensus_stocks = [
            "BEL", "HAL", "DIXON", "TRENT", "POLYCAB",
            "PERSISTENT", "COFORGE", "BHARTIARTL", "TATASTEEL", "RELIANCE"
        ]
        minervini_only = [
            "SUZLON", "ZOMATO", "BHEL", "TATAMOTORS", "SUNPHARMA",
            "MARUTI", "BAJFINANCE", "ADANIENT", "JINDALSTEL", "HCLTECH"
        ]
        momentum_only = [
            "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN",
            "LT", "TITAN", "ITC", "NTPC", "POWERGRID",
            "ONGC", "COALINDIA"
        ]

        all_universe = consensus_stocks + minervini_only + momentum_only + [
            "WIPRO", "TECHM", "ASIANPAINT", "ULTRACEMCO", "GRASIM",
            "HEROMOTOCO", "EICHERMOT", "BRITANNIA"
        ]

        # Stock pricing map
        prices = {
            "BEL": 312.40, "HAL": 4720.50, "DIXON": 14250.00, "TRENT": 7120.00, "POLYCAB": 6890.00,
            "PERSISTENT": 5340.00, "COFORGE": 7450.00, "BHARTIARTL": 1680.00, "TATASTEEL": 158.50, "RELIANCE": 2980.00,
            "SUZLON": 82.50, "ZOMATO": 285.00, "BHEL": 298.00, "TATAMOTORS": 985.00, "SUNPHARMA": 1890.00,
            "MARUTI": 12450.00, "BAJFINANCE": 7420.00, "ADANIENT": 3120.00, "JINDALSTEL": 990.00, "HCLTECH": 1780.00,
            "TCS": 4280.00, "INFY": 1920.00, "HDFCBANK": 1660.00, "ICICIBANK": 1240.00, "SBIN": 815.00,
            "LT": 3720.00, "TITAN": 3780.00, "ITC": 510.00, "NTPC": 425.00, "POWERGRID": 345.00,
            "ONGC": 295.00, "COALINDIA": 515.00, "WIPRO": 540.00, "TECHM": 1620.00, "ASIANPAINT": 3240.00,
            "ULTRACEMCO": 11800.00, "GRASIM": 2680.00, "HEROMOTOCO": 5600.00, "EICHERMOT": 4920.00, "BRITANNIA": 6050.00,
        }

        # 4. Create Run 1: IND-20260924-005 for Minervini
        r1 = db.query(IndicatorScanRun).filter(IndicatorScanRun.public_scan_id == "IND-20260924-005").first()
        if not r1:
            r1 = IndicatorScanRun(
                id=uuid.uuid4(),
                public_scan_id="IND-20260924-005",
                user_id=user.id,
                indicator_id=def1_id,
                indicator_name="Top 5: Minervini Stage-2 VCP [SCAN]",
                universe="nse-755",
                universe_size=len(all_universe),
                timeframe="1D",
                status="completed",
                stage="completed",
                progress_pct=100.0,
                processed_count=len(all_universe),
                total_count=len(all_universe),
                success_count=len(all_universe),
                failed_count=0,
                skipped_count=0,
                matched_count=len(consensus_stocks) + len(minervini_only),
                started_at=now,
                completed_at=now,
                scan_date=now.date(),
            )
            db.add(r1)
            db.commit()
            print("Created r1:", r1.public_scan_id)

            minervini_matches = set(consensus_stocks + minervini_only)
            for sym in all_universe:
                px = prices.get(sym, 1000.0)
                is_m = sym in minervini_matches
                db.add(IndicatorScanResult(
                    id=uuid.uuid4(),
                    run_id=r1.id,
                    symbol=sym,
                    matched=is_m,
                    match_details={"score": 85.0 if is_m else 20.0, "vcp_pct": 18.5 if is_m else 55.0},
                    ohlcv={"open": px * 0.99, "high": px * 1.02, "low": px * 0.985, "close": px, "volume": 1500000},
                    execution_time_ms=12,
                    created_at=now,
                ))
            db.commit()
            print("Inserted r1 results:", len(all_universe))

        # 5. Create Run 2: IND-20260924-006 for Momentum
        r2 = db.query(IndicatorScanRun).filter(IndicatorScanRun.public_scan_id == "IND-20260924-006").first()
        if not r2:
            r2 = IndicatorScanRun(
                id=uuid.uuid4(),
                public_scan_id="IND-20260924-006",
                user_id=user.id,
                indicator_id=def2_id,
                indicator_name="Top 1: App Preset Momentum [SCAN]",
                universe="nse-755",
                universe_size=len(all_universe),
                timeframe="1D",
                status="completed",
                stage="completed",
                progress_pct=100.0,
                processed_count=len(all_universe),
                total_count=len(all_universe),
                success_count=len(all_universe),
                failed_count=0,
                skipped_count=0,
                matched_count=len(consensus_stocks) + len(momentum_only),
                started_at=now,
                completed_at=now,
                scan_date=now.date(),
            )
            db.add(r2)
            db.commit()
            print("Created r2:", r2.public_scan_id)

            mom_matches = set(consensus_stocks + momentum_only)
            for sym in all_universe:
                px = prices.get(sym, 1000.0)
                is_m = sym in mom_matches
                db.add(IndicatorScanResult(
                    id=uuid.uuid4(),
                    run_id=r2.id,
                    symbol=sym,
                    matched=is_m,
                    match_details={"score": 92.0 if is_m else 15.0, "rsi": 64.2 if is_m else 42.0},
                    ohlcv={"open": px * 0.99, "high": px * 1.02, "low": px * 0.985, "close": px, "volume": 2200000},
                    execution_time_ms=10,
                    created_at=now,
                ))
            db.commit()
            print("Inserted r2 results:", len(all_universe))

        print("Seeding comparison runs finished successfully!")
    finally:
        db.close()


if __name__ == "__main__":
    seed_comparison_runs()
