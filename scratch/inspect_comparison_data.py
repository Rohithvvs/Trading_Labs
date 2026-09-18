import asyncio

from sqlalchemy import text

from app.db.session import engine as async_engine


async def main() -> None:
    async with async_engine.connect() as c:
        defs = (await c.execute(text("select count(*) from strategy_definitions"))).scalar()
        runs = (await c.execute(text("select count(*) from strategy_test_runs"))).scalar()
        completed = (
            await c.execute(
                text("select count(*) from strategy_test_runs where lower(status) = 'completed'")
            )
        ).scalar()
        results = (await c.execute(text("select count(*) from strategy_test_results"))).scalar()
        print("definitions", defs)
        print("runs", runs)
        print("completed_runs", completed)
        print("results", results)
        print("--- definitions ---")
        rows = (
            await c.execute(
                text(
                    "select id::text, name, is_preset, user_id::text "
                    "from strategy_definitions order by updated_at desc limit 20"
                )
            )
        ).fetchall()
        for r in rows:
            print(dict(r._mapping))
        print("--- recent runs ---")
        rows = (
            await c.execute(
                text(
                    "select public_run_id, strategy_name, status, strategy_definition_id::text, "
                    "user_id::text, buy_count, universe, start_date, end_date, completed_at "
                    "from strategy_test_runs order by started_at desc limit 15"
                )
            )
        ).fetchall()
        for r in rows:
            print(dict(r._mapping))


if __name__ == "__main__":
    asyncio.run(main())
