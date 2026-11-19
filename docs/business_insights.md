# Business Insights and Recommendations (Phase 7)

This file reads the results already published in `docs/eda.md`, `docs/sql_analysis.md` and `docs/power_bi_dashboard.md`, and turns them into insights and recommendations — the step a Data Analyst takes after the numbers are correct.

**Every number here comes from the synthetic (fake) data.** They are not real findings about any actual business. Where a pattern is interesting, this file says explicitly what it would mean *if* a real dataset showed the same thing, and what would need to be checked before acting on it. Nothing here is a claim about the owner's real skincare business.

## How to read each entry

- **Finding** — the number, and where it is published.
- **Caveat** — a reason to be careful with this number, if one applies.
- **If this held in real data** — a hypothetical recommendation, never a real one.

## 1. Sales Analytics

**Finding.** October was the busiest month (352 orders), and orders are concentrated on weekends, in the 18:00–20:00 window (S1, S5; `docs/eda.md`). Cream (CXE) is the best-selling product at 35% of units (S2). Order value, mixing recorded and estimated amounts, totaled roughly Rs 19.7 lakh for the year (S8; `docs/power_bi_dashboard.md`).

**Caveat.** The synthetic generator was built with a deliberate festive-season peak and weekend/evening boost (`docs/synthetic_data_plan.md`), so finding them back is a check that the method works, not a discovery.

**If this held in real data:** a seasonal and time-of-day peak would suggest timing ad spend and staffing (packing, WhatsApp replies) around those windows, and treating a single best-selling product as the one most worth never running out of stock on.

## 2. Marketing Analytics

**Finding.** Cost per messaging conversation ranged Rs 15.31–16.02 across campaigns before the Power BI fix, and Rs 15.70 after correctly excluding the two Instagram-boost campaigns that spent money but started no conversations (M2; `docs/power_bi_dashboard.md`, section 7). Weekly ad spend and weekly WhatsApp orders move together, correlation 0.86 (M4–M6).

**Caveat.** This correlation is a demonstration, not a discovery — the generator deliberately links weekly spend to weekly order volume (`docs/eda.md`, section 5). On real data, a similar number would still only show a pattern: nothing in this schema links one ad to one order, so it is never proof that spend caused those orders.

**If this held in real data:** a correlation this strong would be worth investigating with a controlled test (for example, a week with ads paused) before treating it as a reason to increase spend — correlation alone is not a safe basis for a budget decision. A campaign-type mismatch like the Instagram-boost one (spend with no conversation metric to divide it by) is also a sign to check whether a campaign is being measured on the right objective at all, before judging its cost.

## 3. Customer Analytics

**Finding.** 23.80% of identified customers placed more than one order, with a median of 85 days between the first and second order (C1, C2). What repeat customers buy on their second order, by unit share, is broken down in `sql/09_customer_analysis.sql` (C3) — a question Phase 4's Python analysis never covered.

**Caveat.** New-vs-returning counts (C4) always look weighted toward "new" in the early months of any dataset, purely because there has been less time for a second order yet — not because loyalty is falling. The reverse rise later is not loyalty growing either; it is the dataset maturing.

**If this held in real data:** an 85-day median gap between first and second orders would suggest a reminder message (WhatsApp or otherwise) timed before that gap closes, rather than waiting for the customer to come back on their own. A C3-type finding about what repeat customers buy next would inform what to suggest at the point of a second order.

## 4. Profitability Analytics

**Finding.** Every product shows exactly a 60% Prepaid gross margin (P1). Estimated gross profit across all 8 products is roughly Rs 1,241,030 (P2). Weekly estimated gross profit minus ad spend is positive across the measured weeks (P3).

**Caveat.** The uniform 60% margin is not a finding — the synthetic generator sets every product's cost at exactly 40% of its Prepaid price, so a perfectly flat number across every product is guaranteed by construction (`docs/sql_analysis.md`, section 6). COD margins vary more (64–70%) only because COD prices were not set as a fixed markup — also an artifact of how the data was built, not a business pattern.

**If this held in real data:** a genuinely flat margin across every product would be unusual enough to double-check the cost data itself before trusting it; real product costs rarely land on an identical ratio by coincidence. P2 and P3 both depend on estimated, not recorded, costs and values — a real decision about which products to push would need at least the recorded Prepaid revenue, not the estimate alone.

**Needs data (P4, P5).** Gross margin alone cannot show confirmed profit: return costs and confirmed payment records aren't in this schema yet. On the private data, this becomes answerable once Delhivery's COD remittance reports (which show what was actually collected and what was returned) are loaded into `shipments`.

## 5. Payment and Shipping Analytics

**Finding.** 58.75–59% of orders with a known payment type are COD (D1). Delhivery (COD) delivers 86.74% of shipments; Speed Post (Prepaid) delivers a higher share still (D5, D6; `docs/power_bi_dashboard.md`). COD amount to collect runs to real money per week, but it is a collectible amount, not confirmed revenue (D4).

**Caveat.** D4's figure must never be read as revenue — a COD parcel can be marked delivered by the courier and still be refused or returned unpaid at the door, a case this schema does not yet capture (P4).

**If this held in real data:** a meaningfully lower delivery rate on COD versus Prepaid would be worth investigating by district (D2) before assuming it's a courier-wide issue — in this synthetic data, some states lean more COD than others, and a courier's performance in one region is not necessarily its performance everywhere.

## 6. What it would take to make this real

This entire file is built on synthetic data by design (`docs/synthetic_data_plan.md`). To turn any of it into an actual insight about the owner's business, the same Phases 3–6 pipeline would need to run against `marketpulse_private` with:

- Confirmed Prepaid and COD amounts from actual WhatsApp orders (most are currently missing or estimated, `docs/data_cleaning.md`, section 7).
- Delhivery and Speed Post delivery/return records loaded into `shipments`.
- Meta Ads export data loaded into `ad_performance`, matched by week to real order dates.

Even then, every caveat above still applies: an estimate stays labelled as an estimate, a COD amount stays "to collect," and a spend/orders correlation stays a pattern, never proof.

## 7. How this file was checked

Every figure in this file is copied from an already-published, already-tested result (`docs/eda.md`, `docs/sql_analysis.md`, `docs/power_bi_dashboard.md`), not recomputed here. Nothing in this file touches the database.
