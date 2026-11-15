# Dataset Sources

This file records every dataset considered or used in MarketPulse Analytics.

Last checked: 15 November 2026.

## Current status

- One public dataset has been downloaded: the India Post PIN code directory (dataset 4 below), used only as a lookup list.
- The main analysis is planned around the owner's private business data, which never enters this repository. See `data_privacy.md`.
- The public portfolio will use fully synthetic data. See `synthetic_data_plan.md`. The public datasets below are kept as a record of the research.

## Candidate public datasets

### 1. Brazilian E-Commerce Public Dataset by Olist

| Item | Detail |
|---|---|
| Link | https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce |
| Publisher | Olist, on Kaggle |
| Contents (from third-party descriptions) | About 100,000 orders from 2016 to 2018, in 9 linked CSV files: orders, order items, customers, sellers, products, payments, reviews and geolocation |
| Licence | **Not verified.** The Kaggle page could not be read automatically. One third-party page says CC BY-NC-SA 4.0 (non-commercial, share-alike). |
| Fits modules | Sales, Customer, Payment and Shipping. Partly Profitability (prices and freight, but no product costs). |
| Limits | No advertising data. Brazilian market, not Indian. No COD and prepaid split like the owner's business. |
| Status | Candidate. Not downloaded. |

**To do before use:** open the Kaggle page in a browser and copy the exact licence text here.

### 2. Online Retail II (UCI Machine Learning Repository)

| Item | Detail |
|---|---|
| Link | https://archive.ics.uci.edu/dataset/502/online+retail+ii |
| Publisher | Daqing Chen, donated to UCI in 2019 |
| Contents | 1,067,371 rows of transactions from a UK online retailer, from December 2009 to December 2011 |
| Columns | InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country |
| Licence | **Verified on the UCI page:** Creative Commons Attribution 4.0 International (CC BY 4.0). Sharing and adaptation are allowed for any purpose if credit is given. |
| Citation | Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D |
| Fits modules | Sales, Customer (repeat purchases). |
| Limits | No payment, shipping, cost or advertising data. UK market. Invoices starting with "C" are cancellations and need care. |
| Status | Optional candidate. Not downloaded. |

### 3. Marketing Campaign Results (Maven Analytics)

| Item | Detail |
|---|---|
| Link | https://mavenanalytics.io/data-playground/marketing-campaign-results |
| Original source | Jack Daoud, via Kaggle (https://www.kaggle.com/jackdaoud/marketing-data). Not checked. |
| Contents | One CSV table about customer profiles, product preferences, channels and campaign responses |
| Size | Unclear. The page shows "499 records, 25 fields" but its description says 2,240 customers. |
| Licence | The Maven page states "License: Public Domain". The original Kaggle page was not checked. |
| Fits modules | Marketing, only partly. |
| Limits | Customer-level campaign responses. It does **not** contain advertising spend, impressions or clicks, so it cannot support cost-per-order analysis. |
| Status | Weak fit. Not downloaded. |

### 4. All India Pincode Directory (India Post)

This dataset is not for analysis by itself. It is a lookup list: the WhatsApp parser uses it to find the district and state of an order from its PIN code. See `whatsapp_parser_plan.md`, section 9.

| Item | Detail |
|---|---|
| Link | https://www.data.gov.in/catalog/all-india-pincode-directory |
| Publisher | Department of Posts, Government of India, on the Open Government Data Platform India |
| Contents (checked in the downloaded file) | One row per post office: 165,627 rows covering 19,586 PIN codes. Columns: `circlename`, `regionname`, `divisionname`, `officename`, `pincode`, `officetype`, `delivery`, `district`, `statename`, `latitude`, `longitude` |
| Downloaded | 15 November 2026, by the owner in a browser. Saved in `data/raw/` (ignored by Git) as `5c2f62fe-5afa-4119-a499-fec9d604d5bd.csv` |
| How it is used | `python/prepare_pin_codes.py` reduces it to one row per PIN code (`pin_code`, `district`, `state`), saved in `data/processed/pin_codes.csv` (ignored by Git) |
| Licence name | **Verified by the owner in a browser on 15 November 2026.** The data.gov.in page footer states that content is "licensed under the Government Open Data License-India" (GODL-India) |
| Licence terms | **Partly verified by the owner on 15 November 2026**, from the licence text at https://www.data.gov.in/Godl: commercial use is allowed, subject to the licence conditions. The exact credit line required has not been recorded yet |
| Fits modules | Sales, Customer, Payment and Shipping (all location analysis) |
| Limits | Of the 19,586 PIN codes, 18,228 (93%) have one clear district and state. For 1,358 the post offices list more than one district or none, so the district is left empty and such orders are flagged. For 152 the state is also unclear. District names are in capitals, and "NA" in the source means not available. The official pages refuse automated reading, so the file must be downloaded by hand |
| Status | Downloaded. In use as a lookup list for the WhatsApp parser. |

**To do before use:** record here the exact credit line that the licence requires.

A small hand-written sample, `data/synthetic/synthetic_pin_code_sample.csv`, is used to test the parser. It holds about ten well-known city PIN codes and is not taken from the official file.

## Main finding

No reliable public dataset was found that contains real e-commerce advertising spend similar to Meta Ads messaging campaigns. For the public portfolio, marketing data will have to be synthetic and clearly labelled.

## Other datasets seen but not checked

These appeared in search results. Their quality and licences have not been checked.

- Mendeley ROAS optimisation dataset: https://data.mendeley.com/datasets/jpz9kcnrhd
- Figshare multi-region marketing mix dataset: https://figshare.com/articles/dataset/Multi-Region_Marketing_Mix_Modeling_MMM_Dataset_for_Several_eCommerce_Brands/25314841

## Rules for this file

- Add a dataset here before downloading it.
- Record the link, licence, contents and limits.
- Mark a licence as "verified" only after reading it on the official page.
- Label synthetic data as synthetic everywhere it is used.
