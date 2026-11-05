"""Your work goes here: the weekly report and its cache.

Rules (see the README):
- Read raw rows only through `scan_raw()`.
- Keep your cache in DuckDB tables on `db`, holding aggregated results.
- You decide what to cache, when to fill it, and how to refresh it.

`app/main.py` calls these three functions. Add any helpers you need.
"""

from datetime import date, timedelta

from app.raw import db, scan_raw  # noqa: F401


def startup() -> None:
    dates = [date(2025, 2, 10) + timedelta(days=i) for i in range(39)]  # sampai 2025-03-20
    db.execute("CREATE TABLE IF NOT EXISTS day_agg (shop_id VARCHAR, date DATE, revenue BIGINT, units BIGINT)")
    with scan_raw("base", dates) as t:
        db.execute(f"""
            INSERT INTO day_agg
            SELECT shop_id, date, SUM(revenue), SUM(units_sold)
            FROM (SELECT DISTINCT * FROM {t})
            GROUP BY shop_id, date
        """)
    

def weekly_report(shop_id: str, week_start: date) -> dict:
    """Return the report for one shop and one ISO week.

    `week_start` is the Monday of the requested week. The result must include
    `revenue` and `units` (integers) and `revenue_wow_pct` (a number or None).
    """
    raise NotImplementedError("weekly_report is not implemented yet")


def on_delta_loaded() -> None:
    """Called by POST /load-delta, after the delta is available as source "delta".

    Return only when every report is up to date.
    """
    raise NotImplementedError("on_delta_loaded is not implemented yet")
