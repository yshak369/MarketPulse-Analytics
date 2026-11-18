# SQL Business Analysis (Phase 5)

This file explains the five `sql/08`–`12` analysis files: what each query answers, the technique it uses, and how it was checked. They read the `clean` schema directly in plain SQL — no Python involved.

All counts in this file come from the **synthetic (fake) data**. They are not real business results.

## 1. Why this phase exists alongside the Python analysis

Phase 4 (`python/eda.py`) already answered these questions in pandas. Phase 5 answers the same questions again, independently, in SQL. This is deliberate, not duplication:

- **SQL is a listed project skill** (CLAUDE.md), so it gets its own complete, standalone deliverable in `sql/`, not just the loading scripts from earlier phases.
- **Two tools, one answer, is a real test.** Every overlapping question was run against the same database and checked against the numbers already published in `reports/eda_synthetic/`. They all matched.
- **Two questions Phase 4 never answered.** `C3` (what repeat customers buy on their second order) and the whole Profitability module (`P1`–`P3`) are new here.

## 2. How to run these files

```
psql -U marketpulse_user -d marketpulse_synthetic -h localhost -f sql/08_sales_analysis.sql
psql -U marketpulse_user -d marketpulse_private -h localhost -f sql/09_customer_analysis.sql
```

Each file runs independently and reads only `clean.*`. There is no safety guard to refuse a target schema, unlike the import and cleaning scripts: every statement is a read-only `SELECT`, so there is nothing to write and nothing to protect against.

**Privacy.** Unlike the Python scripts, a plain `SELECT` prints its result rows straight to the terminal. The `clean` schema holds no personal details (Phase 3), but it does hold real money, district and campaign figures. Running these files against `marketpulse_private` is exactly like looking at the numbers in pgAdmin: fine on the owner's own screen, never pasted into a chat, never committed (`docs/data_privacy.md`).

## 3. The files

| File | Questions | Covered in Phase 4 too? |
|---|---|---|
| `sql/08_sales_analysis.sql` | S1–S8 | Yes |
| `sql/09_customer_analysis.sql` | C1, C2, C4, C5, and the new **C3** | C1, C2, C4, C5 yes; C3 is new |
| `sql/10_profitability_analysis.sql` | P1, P2, P3 — a module Phase 4 never built | No, entirely new |
| `sql/11_payment_and_shipping_analysis.sql` | D1–D6 | Yes |
| `sql/12_marketing_analysis.sql` | M1–M6 | Yes |

`P4` and `P5` stay "Needs data" (`docs/business_questions.md`): no return-cost or confirmed-payment records exist anywhere in the schema, so there is nothing to query for them yet.

## 4. Techniques, matched to their pandas equivalent

Nothing here was invented fresh — each SQL feature does the same job as a specific line in `python/eda.py`, using what is already built into stock PostgreSQL 18 (no extension):

| SQL | Matches | Used in |
|---|---|---|
| `generate_series()` for a date spine, `LEFT JOIN ... COALESCE(..., 0)` | `pd.date_range()` + `.reindex(fill_value=0)` | Every weekly/monthly table, so a quiet period shows as 0, never a gap |
| `AVG() OVER (ORDER BY ... ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)` | `.rolling(4).mean()` | S1's 4-week trend |
| `percentile_cont(fraction) WITHIN GROUP (ORDER BY ...)` | `np.percentile()` | S7, C2, D3, D6 |
| `corr(x, y)` | `np.corrcoef()` | M4–M6's spend/orders correlation |
| A self-join on `order_items` (`b.product_code > a.product_code`) | `itertools.combinations()` on `sorted(set(codes))` | S3's product pairs |
| `FILTER (WHERE ...)` | boolean masking / `.where()` | Splitting written vs defaulted units, COD vs Prepaid, by `value_basis` |
| A window function wrapping a filtered aggregate (`sum(sum(x) FILTER (...)) OVER ()`) | `pivot_table()` + a share calculation | D3's product mix, in one pass, no correlated subquery |

## 5. Cross-checked results (synthetic data)

A sample of the exact matches between this phase and Phase 4's already-published numbers:

| Question | SQL result | Phase 4 result |
|---|---|---|
| S1 | October 2025 peaks at 352 orders | Identical (`reports/eda_synthetic/S1_month.csv`) |
| C1 | 23.80% repeat share, 23.44% without duplicates | Identical |
| D1 | 59% of known-payment orders are COD | Identical |
| D6 | Delhivery median 4 days, Speed Post median 5 days | Identical |
| M2 | Rs 15.31–16.02 per conversation across 5 campaigns | Identical |
| M4–M6 | Correlation 0.8605 | 0.86 (same value, rounded) |

And two internal cross-checks for the new Profitability module, which had nothing in Phase 4 to compare against:

- P3's 53 weekly `ad_spend` figures sum to **Rs 422,947.96** — the same grand total as M1's already-validated spend.
- P2's 8 product rows sum to **Rs 1,241,030.00** — matching a separately computed total straight from `order_items`.

## 6. A real finding, and why it isn't one

P1 shows every product with **exactly a 60% Prepaid gross margin**. This is not a business insight: the synthetic generator (`python/generate_synthetic_data.py`) sets every product's `unit_cost` to exactly 40% of its Prepaid `selling_price`, so a uniform 60% margin is guaranteed by construction. COD margins vary more (64–70%) because COD prices were not set as a fixed markup. Worth remembering before reading too much into a suspiciously tidy number in any dataset.

## 7. How it was tested

- Every file was run against `marketpulse_synthetic` and its results checked line by line against `reports/eda_synthetic/` (section 5 above).
- Every file was also run against `parser_test_clean`, a much smaller, messier schema, to confirm no error on edge cases: ties in a ranked list (S6's district order was non-deterministic before a tiebreaker was added — caught by running the same file twice and comparing), zero matching rows for a `HAVING` threshold (C5), and zero rows in `shipments` or `ad_performance` (D5, D6, M1–M6).
- Two risk points specific to empty ad data were tested directly rather than assumed: `generate_series(min(x), max(x), ...)` over an empty table returns 0 rows, and `corr()` over 0 rows returns `NULL` — neither errors.
- Where no earlier figure existed to compare against (P2, P3), the results were cross-checked against each other and against an independently computed grand total (section 5).

## 8. Known limits

- **No automated test suite.** Unlike the Python code, these `.sql` files have no `unittest`-style tests of their own. Verification is the manual, documented cross-check above, matching how the earlier loading scripts (`sql/01`–`07`) were checked by running them and inspecting the result, not by a test framework.
- **These files print real data when run privately**, by design (section 2). They are not meant to be scripted into an automated pipeline that could leak their output; a person runs them and reads the result.
