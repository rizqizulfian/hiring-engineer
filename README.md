# Weekly report with a cost-aware cache

Take-home for Nesra Scale (Software Engineer). All of my work is in `app/reports.py`
and `tests/test_reports.py`. The original task description is in the git history
of this repository (first commit).

Result: `measure.py` **PASS**, total **Rp 14,505.95** (budget: under Rp 20,000),
13,500 requests, 100% correct, 0 stale.

## Cache design

**What is cached.** One DuckDB table: `day_agg(shop_id, date, revenue, units)`,
the total revenue and units per shop per day. A day is the smallest piece that
can be added up into any week, and when a day is corrected only that day's rows
have to be replaced. Reports never read raw rows once the cache is filled.

**Precompute at startup.** `startup()` scans the base data once for W07 to W12
(2025-02-10 to 2025-03-20, 226,163 rows) and sums per shop per day. W07 is
included because it is the "last week" of W08. Older weeks are never requested,
so scanning all 90 days (Rp 25,810) would waste most of the budget.
If `day_agg` already exists, `startup()` returns immediately, so calling it
again (for example by a second `TestClient`) does not double the totals or
cost anything.

**Serving a report.** `weekly_report()` adds up the 7 days of the requested week
and the 7 days of the previous week from `day_agg` (Rp 0 per request). A shop or
week without rows gives `0, 0`. WoW is computed when the report is read:
`100 * (this - last) / last`, and `null` when last week's revenue is 0.
I do not store WoW because it is derived from two weekly totals: storing it
would mean updating it in two places whenever one day is corrected.

**When the delta arrives** (`on_delta_loaded()`), step by step:

1. Scan the whole delta (17,458 rows) and collect the dates it contains:
   3 new days (03-21 to 03-23) and 8 older days that have corrections.
2. Scan the base data only for those dates (46,498 rows). The new days have
   no base rows, so they cost nothing there.
3. For those dates, merge: base rows whose key `(shop_id, product_id, date)`
   is not in the delta, plus all delta rows. Delta rows replace base rows.
4. Inside one transaction, delete those dates from `day_agg` and insert the
   recomputed totals. On any error the transaction is rolled back, so a
   report never sees a half-updated cache.

Only 11 days are recomputed. Every other day stays cached and costs nothing.
Recomputing all 90 days instead would cost Rp 26,683 and fail the budget.
Reports for older weeks (W10 and W11) are corrected too, because the corrected
days are inside those weeks.

## Cost

`measure.py` scorecard (fresh service):

| | Rp |
| :-- | --: |
| Startup (226,163 rows) | 11,308.15 |
| Phase 1, 7,500 requests | 0.00 |
| Delta (17,458 + 46,498 rows) | 3,197.80 |
| Phase 2, 6,000 requests | 0.00 |
| **Total** | **14,505.95** |

13,500 requests, correct 100% (7422/7422 before, 5943/5943 after the delta),
0 stale keys. Latency p50 about 12 ms.

**Naive version (no cache).** Each report scans its week and the previous week:
about 80,000 rows, roughly Rp 4,000 per request. For the same 13,500 requests
that is about **Rp 53.5 million**, around 2,700 times the budget. For the
production load in the task (500 shops, 20 requests a day, 30 days = 300,000
requests) it is about Rp 1.17 billion a month, assuming requests are spread
evenly over the weeks.

## Data issues

I profiled the data before choosing the design. What I found, and what I did:

- **69 exact duplicate rows** in the base data, on 4 shop-days (SHP285014,
  SHP866221, SHP422010, SHP332806). I remove them with `SELECT DISTINCT`
  before summing, which is what the reference in `measure.py` does.
- **12 correction rows** in the delta that overwrite base rows (same shop,
  product and date) on 8 older dates. 9 change the numbers, 3 are identical.
  Delta rows win.
- **3 rows with negative revenue** (negative price) and **3 rows with price 0**
  and units sold. I keep them as they are, since I cannot tell if they are
  errors or returns and the reference also keeps them.
- **NULL `ad_spend`** in about 0.7% of rows. Not used by the report.
- **Partial week W12** (base ends 03-20, delta adds 03-21 to 03-23). I count
  whatever days exist.
- `measure.py` marks some shop-weeks as `data_issue`. I explained three of
  the six shops (negative revenue or price 0). For SHP042488, SHP483681 and
  SHP860524 I did not find a cause.
- Some shops have revenue 0 in a week (or no rows at all), so WoW is `null`
  for the following week.

## Tests

`tests/test_reports.py` (run `uv run pytest -v`):

- Calling `startup()` twice does not double the cache or add cost.
- After `POST /load-delta` the extra scan is exactly 63,956 rows, and the
  corrected week changes (SHP141660, W10: revenue 429,524,900 to 429,344,900,
  units 1,819 to 1,818).

## Trade-offs

- **Daily totals vs weekly totals.** Daily rows are a bit bigger than weekly
  ones (7x rows) but a correction touches one day, and any week can be built
  from them. Weekly totals would force recomputing a whole week for one
  corrected row.
- **Precompute vs on-demand.** Precomputing W07 to W12 costs Rp 11,308 up front
  even for shops nobody opens, but serving is free and predictable. On-demand
  filling would save that if few reports are opened, but the first request of
  each week would pay for a scan.
- **Precise refresh vs flush everything.** Refreshing only the dates in the
  delta is cheaper (Rp 3,198 vs Rp 26,684) but depends on trusting that the
  delta lists every changed date. Flushing is simpler and safer, and too
  expensive here.
- **Compute WoW on read vs store it.** Computing it is almost free and cannot go
  stale; storing it would be one more thing to invalidate.
- **In memory.** Same lifetime as the raw data in this starter, so there is no
  inconsistency to handle, but a restart means paying the startup cost again.

## Next steps

- Persist the cache (a DuckDB file or a warehouse table) so a restart does not
  repeat the Rp 11,308 startup scan.
- Make `on_delta_loaded()` retryable if it fails halfway.
- Refresh only the dates whose rows really changed (3 of the 12 corrections
  are identical to the base).
- Add tests for edge cases: shop without rows, WoW `null`, delta loaded twice.
- Extend the cache automatically when new weeks arrive, instead of a fixed
  W07 to W12 window.

## Notes

**AI use.** I used Claude Code (Claude Sonnet 5.5) for most of this work, and I
want to be clear about who did what.
- **Claude** read the repository, profiled the data (duplicates, corrections,
  row counts per date), built the cost model and proposed the design: a daily
  aggregate table, precompute for W07 to W12, and a delta refresh that only
  recomputes the dates the delta touches.
- **Me:** While Claude was analysing, I read the repository, skimmed the data
  and thought about the design myself. I chose to implement `app/reports.py` and the tests myself, step by
  step with Claude explaining each part. I ran everything locally, checked the
  numbers against `/stats` and `measure.py`, and wrote the tests that prove the
  cache is not doubled and that the delta refreshes the corrected week.
- Claude also helped me review my code and write this README. I read and edited
  the result, and I can explain the trade-offs (why daily totals, why WoW is not
  stored, why the delta refresh is one transaction) and change any line live.

**Not done / limits.**
- The cache lives in memory (same as the raw data), so a restart loses both.
  I did not make it persistent.
- Only W07 to W12 are cached, which is what the task requests.
- If `on_delta_loaded()` fails halfway, the rollback keeps the old cache, but
  the starter marks the delta as loaded, so a second POST cannot retry it.
