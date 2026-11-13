# Data Privacy Approach

This file explains how MarketPulse Analytics uses real business data without exposing customers.

## The main idea

The project has two separate environments. Both use the same database schema, the same SQL and Python code, and the same dashboard design.

| | Private environment | Public environment |
|---|---|---|
| Where | The owner's computer only, in a folder outside this repository | This GitHub repository |
| Data | Real WhatsApp orders, advertising spend, costs | Synthetic or public data, clearly labelled |
| Purpose | Analyse the real business | Show the method and skills to recruiters |
| Shared with | Nobody | Everybody |

## Private data sources

| Source | What it gives | How it is exported | Privacy level |
|---|---|---|---|
| WhatsApp groups (Prepaid and COD) | Orders, products, quantities, locations, COD amounts to collect | Chat export, then the parser | High: customer details |
| Meta Ads Manager | Daily spend, impressions and messaging conversations by campaign | CSV export | Medium: no customer data, but confidential business figures |
| Shopify | Website orders, product catalogue and selling prices | CSV export | High: customer details |

Notes:

- Shopify orders are separate from WhatsApp orders, so the two can be added together without double counting.
- Shopify selling prices may be used to estimate prepaid order value. Any such value is labelled as an estimate.
- Advertising cannot be linked to individual orders, because nothing records which ad led to which order. Advertising is compared with orders by day or week only. No per-order attribution is claimed.
- The time period covered by each source is still to be confirmed.

## What never goes into this repository

- Customer names, phone numbers and addresses
- PIN codes linked to individual orders
- Raw WhatsApp chat exports
- Parser output made from real chats
- Real order-level records of any kind
- Exact business revenue, advertising spend or profit figures, unless the owner decides to share a specific aggregated number

## Rules for real data

1. Real data stays in a private folder outside this project folder. The exact location is still to be chosen.
2. Real data is never committed to Git or pushed to GitHub.
3. Real data is never uploaded or pasted into an external AI service, including coding assistants.
4. Code is written and tested with fake examples. The owner then runs it on the real data locally.
5. The `data/raw` and `data/processed` folders are ignored by Git as a second safety layer.

## Anonymisation rules

Removing names is not enough. If real data is ever used to build a public dataset, all of these apply:

- Remove names, phone numbers and full addresses.
- Replace customer and order IDs with new random IDs. Do not use hashed phone numbers, because a hash of a phone number can be reversed by trying all possible numbers.
- Reduce location detail, for example keep only the district or state.
- Shift or group dates so a single order cannot be matched to a real day.
- Check for rare combinations, such as a small town with only one or two orders, and group or remove them.
- Review the result by hand before publishing.

The preferred option is simpler and safer: generate fully synthetic data that follows the same structure, and use no real rows at all.

## Rules for synthetic data

- Synthetic data is labelled as synthetic in the file name, the README and the dashboard.
- Synthetic results are never presented as real business results.
- Advertising attribution and business outcomes are never invented and shown as real.

## Honest reporting

- Missing values stay "unknown". They are not filled with guesses.
- Estimates are labelled as estimates.
- A COD collectible amount is the amount to be collected. It is not confirmed revenue.

## Checks before publishing to GitHub

- [ ] `git status` shows no data files.
- [ ] No real name, phone number or address appears in any file, including examples and screenshots.
- [ ] Dashboard screenshots show only synthetic or approved aggregated data.
- [ ] Every synthetic dataset is labelled.
