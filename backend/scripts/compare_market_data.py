#!/usr/bin/env python3
"""Compare market data and indicator parity between Local and Production backends.

Usage:
    python backend/scripts/compare_market_data.py
    python backend/scripts/compare_market_data.py --remote https://trading-labs.onrender.com --symbols MOTILALOFS,CARTRADE,CHENNPETRO,RELIANCE
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from typing import Any


def fetch_parity(base_url: str, symbols: str, trade_date: str | None = None) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/market-data/parity?symbols={symbols}"
    if trade_date:
        url += f"&trade_date={trade_date}"
    req = urllib.request.Request(url, headers={"User-Agent": "TradingLabsParityChecker/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Local vs Production market data parity.")
    parser.add_argument("--local", default="http://127.0.0.1:8000", help="Local backend URL")
    parser.add_argument("--remote", default="https://trading-labs.onrender.com", help="Production backend URL")
    parser.add_argument("--symbols", default="MOTILALOFS,CARTRADE,CHENNPETRO,RELIANCE,TCS", help="Comma-separated symbols")
    parser.add_argument("--date", default=None, help="Target trade date (YYYY-MM-DD)")
    args = parser.parse_args()

    print("=" * 80)
    print("MARKET DATA PARITY CHECK")
    print(f"Local URL:      {args.local}")
    print(f"Production URL: {args.remote}")
    print(f"Symbols:        {args.symbols}")
    print("=" * 80)

    try:
        print("\nFetching data from Local backend...")
        local_data = fetch_parity(args.local, args.symbols, args.date)
        print(f"  Local Backend: {local_data.get('backend')}, as_of: {local_data.get('as_of')}")
    except Exception as exc:
        print(f"  ERROR fetching from Local: {exc}")
        local_data = None

    try:
        print("\nFetching data from Production backend...")
        remote_data = fetch_parity(args.remote, args.symbols, args.date)
        print(f"  Production Backend: {remote_data.get('backend')}, as_of: {remote_data.get('as_of')}")
    except Exception as exc:
        print(f"  ERROR fetching from Production: {exc}")
        remote_data = None

    if not local_data and not remote_data:
        print("\nCould not reach either backend.")
        return 1

    if local_data and not remote_data:
        print("\nOnly Local data available:")
        print(json.dumps(local_data, indent=2))
        return 0

    if remote_data and not local_data:
        print("\nOnly Production data available:")
        print(json.dumps(remote_data, indent=2))
        return 0

    # Compare symbols
    local_syms = local_data.get("data", {})
    remote_syms = remote_data.get("data", {})
    all_syms = sorted(set(list(local_syms.keys()) + list(remote_syms.keys())))

    mismatches = 0
    print("\n" + "=" * 80)
    print(f"{'SYMBOL':<15} {'FIELD':<12} {'LOCAL':<20} {'PRODUCTION':<20} {'STATUS'}")
    print("-" * 80)

    for sym in all_syms:
        loc = local_syms.get(sym, {})
        rem = remote_syms.get(sym, {})

        loc_status = loc.get("status")
        rem_status = rem.get("status")

        if loc_status != rem_status:
            print(f"{sym:<15} {'status':<12} {str(loc_status):<20} {str(rem_status):<20} MISMATCH")
            mismatches += 1
            continue

        if loc_status != "OK":
            print(f"{sym:<15} {'status':<12} {str(loc_status):<20} {str(rem_status):<20} BOTH {loc_status}")
            continue

        # Compare date, close, rsi, sma50, sma200
        checks = [
            ("date", loc.get("date"), rem.get("date")),
            ("close", loc.get("close"), rem.get("close")),
            ("rsi_14", loc.get("indicators", {}).get("rsi_14"), rem.get("indicators", {}).get("rsi_14")),
            ("sma_50", loc.get("indicators", {}).get("sma_50"), rem.get("indicators", {}).get("sma_50")),
            ("sma_200", loc.get("indicators", {}).get("sma_200"), rem.get("indicators", {}).get("sma_200")),
        ]

        for field, l_val, r_val in checks:
            match = True
            if l_val is None and r_val is None:
                match = True
            elif l_val is None or r_val is None:
                match = False
            elif isinstance(l_val, (int, float)) and isinstance(r_val, (int, float)):
                match = abs(float(l_val) - float(r_val)) < 0.05
            else:
                match = str(l_val) == str(r_val)

            status_str = "MATCH" if match else "MISMATCH"
            if not match:
                mismatches += 1
            print(f"{sym:<15} {field:<12} {str(l_val):<20} {str(r_val):<20} {status_str}")

    print("=" * 80)
    if mismatches == 0:
        print("ALL COMPARISONS MATCH PERFECTLY! Parity verified.")
        return 0
    else:
        print(f"FOUND {mismatches} MISMATCHES between Local and Production.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
