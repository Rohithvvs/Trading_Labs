from app.db.session import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    r = db.execute(text("select version_num from alembic_version")).fetchall()
    print("alembic_version:", r)
    col = db.execute(
        text(
            "select column_name from information_schema.columns "
            "where table_name='recommendation_engine_decisions' "
            "and column_name='technical_analysis'"
        )
    ).fetchall()
    print("technical_analysis column:", col)
    for t in [
        "event_calendar",
        "user_profiles",
        "veto_history",
        "walk_forward_summary",
        "event_ingestion_run",
    ]:
        e = db.execute(
            text(
                "select exists(select 1 from information_schema.tables "
                "where table_schema='public' and table_name=:t)"
            ),
            {"t": t},
        ).scalar()
        print(f"table {t}:", e)
finally:
    db.close()
