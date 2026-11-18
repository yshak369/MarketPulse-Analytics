# MarketPulse Analytics

An end-to-end e-commerce sales and marketing analytics portfolio project.

It analyses sales, advertising, customer behaviour, product performance and profitability, using SQL, Python, Pandas, NumPy, PostgreSQL and Power BI.

> Status: Phases 1 to 5 complete (project structure, database schema, data importing, data cleaning, exploratory data analysis, SQL business analysis). Phase 6 (Power BI dashboard) not started.

**[Read the synthetic exploratory data analysis report](reports/eda_synthetic/eda_report.md)** — sales, customer, payment and marketing questions answered from the clean, fully synthetic data.

## How the data flows

```
WhatsApp chats ─► parse_whatsapp_orders.py ─┐
Shopify export ─► prepare_shopify_orders.py ─┼─► PostgreSQL raw tables ─► audit + clean_data.py ─► "clean" schema ─┬─► eda.py (Python report)
Meta Ads export ─► prepare_meta_ads.py ──────┘     (sql/01 to 06)          (Python, Pandas)        (sql/07)        └─► sql/08-12 (SQL analysis) ─► Power BI
```

The public version of this project uses **synthetic (fake) data** in exactly the same tables. See `docs/synthetic_data_plan.md`.

## Run it on the synthetic data

From the project folder, with PostgreSQL running and the virtual environment active:

```
python -m pip install -r requirements.txt
python -m unittest discover -s python
python python/audit_data_quality.py --database marketpulse_synthetic --period-start 2025-01-01 --period-end 2025-12-31
python python/clean_data.py --database marketpulse_synthetic
python python/eda.py --database marketpulse_synthetic --output reports/eda_synthetic
psql -U marketpulse_user -d marketpulse_synthetic -h localhost -f sql/08_sales_analysis.sql
```

The cleaning rules, and why each one exists, are explained in `docs/data_cleaning.md`. The exploratory analysis method and its known traps are explained in `docs/eda.md`. The five SQL analysis files (`sql/08`–`12`) are explained, question by question, in `docs/sql_analysis.md`.

## Modules

1. Sales Analytics
2. Marketing Analytics
3. Customer Analytics
4. Profitability Analytics
5. Payment and Shipping Analytics

## Folder Structure

| Folder | Purpose |
|---|---|
| `data/raw` | Original downloaded datasets. Never edited. |
| `data/processed` | Files created by the Python scripts, such as the PIN code list and test output. Ignored by Git. |
| `data/synthetic` | Synthetic (fake) data for the public portfolio. Clearly labelled. |
| `sql` | PostgreSQL schema and analysis queries. |
| `notebooks` | Planned for Jupyter notebooks. Empty for now (see `docs/data_cleaning.md`, section 7). |
| `python` | Reusable Python scripts. |
| `reports` | The published exploratory data analysis report (synthetic data only). |
| `dashboards` | Power BI dashboard and screenshots. |
| `docs` | Dataset sources, insights and written notes. |

## Data Policy

- Public datasets are documented in `docs/dataset_sources.md`.
- Any synthetic data is clearly labelled as synthetic.
- No real customer names, phone numbers or addresses are included.
- No advertising attribution or business results are invented.
