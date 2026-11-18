# Exploratory Data Analysis (Phase 4)

This file explains how `python/eda.py` turns the `clean` schema into answers to the business questions, and how to run it.

All counts in this file come from the **synthetic (fake) data**. They show what the method finds. They are not real business results.

## 1. The idea in one picture

```
clean tables (schema "clean")        a report
  filled by python/clean_data.py  ──► python/eda.py
  never changed by this phase          one function per question (docs/business_questions.md)
                                        Markdown report + PNG charts + CSV files
```

This phase reads the `clean` schema only. It never touches the raw tables or the `clean` schema itself. Phase 5 (SQL analysis) and Phase 6 (Power BI) build on the same questions, in SQL and in a dashboard.

## 2. How to run it

```
python python/eda.py --database marketpulse_synthetic --output reports/eda_synthetic
```

- `--database`: `marketpulse_synthetic` for the public report, `marketpulse_private` for the owner's own data.
- `--output`: where to write the report. The synthetic database may write inside this project, but only to `reports/eda_synthetic/` (the folder this report is published from). Any other database must write outside the project, or under `data/processed/` (ignored by Git) — the same rule the import and cleaning scripts use.
- The console prints counts only: orders counted, charts written, and whether ad or shipment data exists yet.

## 3. Rules for every table and chart

1. **Only counted orders** (`include_in_analysis = true`) are used, unless a table is about the excluded orders themselves.
2. **Every value says where it comes from.** `recorded`, `estimated` or `unknown`. A COD amount is the amount **to collect**, never money received or confirmed revenue.
3. **Results of different kinds are never added together**, and reach is never added across days (the same rules as `docs/data_cleaning.md`).
4. **Ad spend and orders are compared by week only, and the word is "pattern", never "proof".** Nothing in this data links one ad to one order (`docs/schema_design.md`).
5. **Orders with no product line** (set to 1 cream by the owner's rule) are shown apart from what customers actually wrote. **Possible duplicates** are counted, with their flag kept, so repeat-customer figures can be read with or without them.
6. **A result with too little data says so.** No ad rows yet, no shipment rows yet, or too few weeks for a correlation all give an honest message, never a guess or a crash.
7. **Small groups are left out of comparisons**, not shown with a misleadingly confident share: districts need at least 20 customers (C5), states need at least 30 orders (D2). Both minimums can be changed with a function argument.

## 4. The report

One Markdown file, `eda_report.md`, with a section per question from `docs/business_questions.md`: a short factual sentence built straight from the numbers, a chart where a picture helps, and the full table (shown up to 15 rows, with every row in the matching CSV file).

| Section | Questions | Headline synthetic finding |
|---|---|---|
| Sales | S1–S8 | October 2025 was the busiest month (352 orders); Cream is 35% of all units sold; weekends and the 18:00–20:00 slot are busiest |
| Customers | C1, C2, C4, C5 | 23.8% of known customers ordered more than once; a median of 85 days passed before a second order |
| Payment and shipping | D1–D6 | 59% of orders with a known payment type were COD; Delhivery (COD) delivers 80%, Speed Post (Prepaid) 97% |
| Marketing | M1–M6 | Rs 15–16 per messaging conversation across 5 campaigns; weekly ad spend and weekly WhatsApp orders moved together (correlation 0.86) — **a pattern in data built to show one, not evidence that ads cause orders** |

## 5. Known traps worth remembering

- **New vs returning customers (C4).** Returning-customer orders always look low in the first months of any dataset, because there has been less time for a second order — this is not falling loyalty, and the opposite rise is not growing loyalty either. The report states this next to the table every time.
- **The M4–M6 correlation is a demonstration, not a discovery.** The synthetic generator deliberately gives weeks with more orders more ad spend (`docs/synthetic_data_plan.md`), so the found correlation (0.86) only proves the method can detect a pattern that was put there on purpose. On real data, a similar number would still only be a pattern, never proof of cause.
- **Private data will look very different here.** The owner's real WhatsApp data has almost no recorded Prepaid amounts, no ads yet and no shipments yet (see `docs/data_cleaning.md`, section 7), so several sections will report "no data yet" or mostly estimated values until the Meta Ads and Shopify imports, and courier records, are added.

## 6. How it was tested

- One test or more per analysis function, on tiny hand-made tables (`python/test_eda.py`), including a dedicated check that every function returns an empty or zero result — never an error — when there are no counted orders, no ad rows or no shipment rows.
- Key synthetic numbers were checked against independent SQL queries on the `clean` schema: orders per month, units per product, repeat-customer counts, COD share by state, and total ad spend.
- The patterns the synthetic generator deliberately built in were confirmed by the analysis: the weekend boost, the festive-season peak, the evening order rush, higher COD shares in Telangana and Andhra Pradesh, and the spend/orders correlation.
- The report and every chart were read and viewed by hand after generation, which caught two bugs before they were committed: two sub-tables sharing one question code (S1, S6) were showing the same chart and the same sentence, and a dual-axis chart's legend was missing.
- A run on `parser_test_clean` (ad data, no shipment data) produced the correct "no data yet" sections instead of an error.

## 7. Known limits

- **No Jupyter notebook**, for the same reason as Phase 3 (`docs/data_cleaning.md`, section 7): Windows Smart App Control on the development computer blocks a file every notebook needs. The Markdown report and charts serve the same purpose.
- **Nine charts, not one per question.** Every question has a table; a chart is added only where a picture adds something a table cannot show at a glance (a trend, a split, a heatmap). The plan called this "one chart per main question" in that sense, not one chart for every single sub-table.
- **The report never changes the database.** `python/eda.py` opens a read-only connection; it cannot write to `clean` or to the raw tables, by design.
