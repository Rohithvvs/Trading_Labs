import asyncio
import traceback
import uuid

from app.services.strategy_comparison.comparison_service import catalog, compare_slots, list_runs_for_strategy


USER = uuid.UUID("79adb3b9-6205-42f6-949b-01159976f153")


async def main() -> None:
    try:
        cat = await catalog(USER)
        print("strategy_count", cat["strategy_count"])
        for s in cat["strategies"]:
            print(
                "STRAT",
                s["name"],
                "runs",
                s["completed_run_count"],
                "latest",
                (s.get("latest_run") or {}).get("run_id"),
            )
        print("suggestions", cat.get("suggestions"))
        if len(cat["strategies"]) < 2:
            return
        a, b = cat["strategies"][0], cat["strategies"][1]
        runs_a = await list_runs_for_strategy(USER, a["id"])
        runs_b = await list_runs_for_strategy(USER, b["id"])
        print("runs_a", len(runs_a["runs"]), [r["run_id"] for r in runs_a["runs"][:3]])
        print("runs_b", len(runs_b["runs"]), [r["run_id"] for r in runs_b["runs"][:3]])
        if not runs_a["runs"] or not runs_b["runs"]:
            print("NO RUNS")
            return
        body = await compare_slots(
            USER,
            [
                {"strategy_id": a["id"], "run_id": runs_a["runs"][0]["run_id"], "source": "strategy_tester"},
                {"strategy_id": b["id"], "run_id": runs_b["runs"][0]["run_id"], "source": "strategy_tester"},
            ],
        )
        print("slot_count", body["slot_count"])
        for slot in body["slots"]:
            m = slot["metrics"]
            print(
                "SLOT",
                slot["strategy_name"],
                "win",
                m.get("win_rate"),
                "avg",
                m.get("average_trade"),
                "trades",
                m.get("total_trades"),
                "buy",
                (slot.get("scan_summary") or {}).get("buy"),
                "signals",
                len(slot.get("signals") or []),
            )
        print("has_equity", body["has_equity"])
        print("signal_available", body["signals"]["available"], "overlap", body["signals"]["overlap_pct"])
        print("trade_symbols", body["trades"]["symbol_count"])
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
