# WhatsApp Order Parser Plan

Status: approved plan. No code has been written yet.

All examples in this document are fake. No real customer data appears here.

## 1. Purpose

Most orders are collected by hand in two WhatsApp groups: **Prepaid** and **COD**. The parser is a small Python script that turns the exported chat text into clean tables, so the orders can be analysed with SQL, Pandas and Power BI.

The parser runs only on the owner's computer. It uses plain Python and Pandas. It does not use any AI service.

## 2. Confirmed facts about the workflow

| Topic | Confirmed answer |
|---|---|
| Groups | Two groups: Prepaid and COD |
| Format | Both groups use the same customer information format |
| Who posts | The owner only |
| Language | English |
| Phone type | Android (this decides the export timestamp layout) |
| Edits | Messages are not edited |
| Multiple products | Separated by commas |
| COD amount | Written in brackets after each product. It is the total for that product line, not the price per unit |
| Shipping and discounts | Not included in the collectible amount |
| Prepaid amount | Not recorded in WhatsApp |
| Delivery, returns, money received | Not marked in WhatsApp |

## 3. Message layout

Each order is one message with the fields on separate lines.

Fake prepaid example:

```
Test Customer
12 Sample Street, Example Nagar (post)
Sample Taluk
Madurai
625001
9000000001
1 CXE,1 LP
```

Fake COD example (only the last line is different):

```
Test Customer
12 Sample Street, Example Nagar (post)
Sample Taluk
Madurai
625001
9000000001
1 CXE(900),1 LP(250)
```

| Position | Field |
|---|---|
| First line | Name |
| Middle lines | Address (the number of lines can change) |
| Line above the PIN code | District or city |
| 6-digit line | PIN code |
| 10-digit line | Phone number |
| Last line | Products, separated by commas |

## 4. Product list

| Product | How it is written |
|---|---|
| Cream | `CXE` |
| Facewash | `FW` |
| Body lotion | `BL` |
| Lip balm | `LP` |
| Sunscreen | `SS` |
| Serum | Full word `Serum` |
| Kojiglow | Full word `Kojiglow` |
| Moisturizer | Full word `Moisturizer` |

Upper and lower case are treated as the same (`cxe` = `CXE`).

Product line formats:

- Prepaid: `1 cxe` means quantity 1, product CXE, no amount.
- COD: `1 cxe(900)` means quantity 1, product CXE, Rs 900 to collect for that line.

## 5. Parser workflow

1. **Export.** The owner exports each group chat as a text file and saves it in a private folder outside this project.
2. **Read.** The parser reads each file and splits it into messages, each with a date, time and sender.
3. **Filter.** Order messages are separated from normal chat. Unsure messages go to review. They are not dropped.
4. **Extract.** The parser reads each order from the bottom up, because the address length changes:
   1. If the last line matches the product pattern, it is the product line.
   2. The 10-digit line is the phone number.
   3. The 6-digit line is the PIN code.
   4. The line just above the PIN code is the district or city.
   5. The first line is the name.
   6. Everything in between is the address.
5. **Payment type.** Set from the source group, then checked against any payment words in the message.
6. **Validate.** The rules in section 7 are applied. A failed rule adds a flag.
7. **Output.** Two files: clean orders, and a review queue with the reason for each flag.
8. **Manual review.** The owner fixes or confirms the flagged rows.
9. **Later (Phase 2).** Approved rows are loaded into the private PostgreSQL database.

Small clean-ups that do not change meaning are allowed: extra spaces, a dot after the name, and letter case in product codes.

## 6. Data fields

### Orders (one row per order message)

| Field | Source | Notes |
|---|---|---|
| `order_id` | Generated | Random ID, not from WhatsApp |
| `message_datetime` | Export timestamp | When the message was posted |
| `source_group` | File name | `prepaid` or `cod` |
| `payment_type` | Group and message text | `prepaid`, `cod` or `needs_review` |
| `customer_name` | Message | Private only |
| `address` | Message | Private only |
| `district_city` | Message | Public version only after a privacy check |
| `pin_code` | Message | Private only, or shortened for the public version |
| `phone` | Message | Private only |
| `review_flags` | Parser | List of reasons, empty if clean |
| `notes` | Parser | For example `product_defaulted_to_cxe` |
| `raw_message` | Export | Private only, kept to check the parser's work |

### Order items (one row per product line)

| Field | Example | Notes |
|---|---|---|
| `order_id` | (link) | Joins to the order |
| `product_code` | `CXE` | Stored in capitals |
| `quantity` | `1` | Whole number |
| `cod_collectible_amount` | `900` | COD only. Total for the line. Empty for prepaid |

**Important:** `cod_collectible_amount` is the amount to be collected. It is not confirmed revenue.

## 7. Validation rules

A failed rule flags the order for manual review. The parser never guesses a value.

| Rule | Check |
|---|---|
| Phone | 10 digits after removing `+91` or a leading `0`, starting with 6 to 9 |
| PIN code | Exactly 6 digits, not starting with 0 |
| Required fields | Name, address, district or city, PIN code and phone |
| Quantity | Whole number, 1 or more |
| Product code | Must be in the product list. Unknown codes are flagged, not matched to the nearest one |
| COD without amount | A COD group order with no amount is flagged |
| Prepaid with amount | A Prepaid group order with an amount is flagged as a conflict |
| Payment conflict | If the message text disagrees with the group, payment type is `needs_review` |
| Amount | Must be a positive number. Very low or very high values are flagged, using limits set by the owner |
| Duplicates | Same phone and same products within a short time are flagged, not deleted |
| Unreadable message | Sent to review with the raw text |

### Default product rule

This is a business rule set by the owner, not a guess by the parser.

- If an order has no product line, it is treated as **1 cream (CXE)**.
- The order gets the note `product_defaulted_to_cxe`, so these orders can always be seen.
- If it is a COD order, the amount is also missing, so the order is flagged for review.

## 8. What this data can and cannot show

Can show: number of orders, products, quantities, locations, order dates, payment type, and COD amounts to be collected.

Cannot show:

- **Prepaid order value**, because the amount is not recorded in WhatsApp.
- **Confirmed revenue**, because delivery, returns and money received are not marked.

Until other private sources are added (for example Delhivery COD remittance reports, Shopify orders or a price list), revenue is reported as **unknown**. Any estimate must be labelled as an estimate.

## 9. Privacy rules

- Real chat exports and parser outputs stay in a private folder outside this Git project.
- Real customer data is never committed to GitHub.
- Real customer data is never uploaded to an external AI service.
- The parser is built and tested with fake messages only.
- The public portfolio contains the parser code, fake test messages and clearly labelled synthetic data.

## 10. Still to confirm

1. **COD amounts:** assumed to be one amount per product, like `1 CXE(900),1 LP(250)`. To be confirmed that it is never one amount for the whole order.
2. **Private folder:** the exact location is not chosen yet. Suggested: `D:\Private\MarketPulse-Data\`.
3. **Amount limits:** the low and high values that should trigger a flag.
4. **Duplicate window:** how many hours or days count as a "short time".
5. **Revenue sources:** which private records can confirm delivery and payment.
