# WhatsApp Order Parser Plan

Status: approved plan, version 2. Built in Phase 2 as `python/parse_whatsapp_orders.py`.

Version 2 was written after the owner checked the layout of real exported chats. Real chats turned out to be messier than the first plan assumed.

All examples in this document are fake. No real customer data appears here.

## 1. Purpose

Most orders are collected by hand in two WhatsApp groups: **Prepaid** and **COD**. The parser is a small Python script that turns the exported chat text into clean tables, so the orders can be analysed with SQL, Pandas and Power BI.

The parser runs only on the owner's computer. It uses plain Python. It does not use any AI service.

## 2. Confirmed facts about the workflow

| Topic | Confirmed answer |
|---|---|
| Groups | Two groups: Prepaid and COD |
| Payment type | Known from the group the file was exported from |
| Who posts | The owner only |
| Language of orders | English letters. Other chat messages can be in other languages |
| Export style | Android: `DD/MM/YYYY, HH:MM - Sender: text`, 24-hour time |
| Edits | Some messages are edited. WhatsApp adds `<This message was edited>` at the end |
| Bulk posting | Orders are often pasted many at a time, so the message time is when the order was **recorded**, not when the customer ordered |
| Multiple products | Separated by commas |
| `/-` after a product | A writing habit with no meaning. It is ignored |
| No product line | Very common. It means 1 cream (CXE) |
| COD amount | Written in brackets after a product. It is usually the total for that product line, not the price per unit. Sometimes an order with several products has only one bracket, which holds the total for the whole order |
| COD product without brackets | No amount was written. The owner's rule: the product can be taken at its normal COD price. That value is an estimate and is labelled as one |
| Normal prices | A product has one normal price for COD and a different one for Prepaid |
| Shipping and discounts | Not included in the collectible amount |
| Prepaid amount | Not recorded in WhatsApp |
| Delivery, returns, money received | Not marked in WhatsApp |
| Other content | The chats also hold notes, links, advert text, price lists, stock tallies and media |

## 3. Message layouts

An order is a message with the customer details on separate lines. The parser must accept all of these layouts.

**Layout A: the usual one** (fake prepaid example)

```
14/03/2025, 19:20 - Owner: Test Customer
12 Sample Street, Example Nagar
Sample Taluk
Madurai
625001
9000000001
1 cxe/-, 1 LP
```

**Layout B: COD amounts** (only the last line is different)

```
1 CXE(900),1 LP(250)
```

**Layout C: no product line, phone above the PIN code, two phones**

```
14/03/2025, 19:21 - Owner: Second Customer
7 Example Road
Sampleville
+91 90000 00002
9000000003
600 001
```

**Layout D: labels**

```
14/03/2025, 19:22 - Owner: Name: Third Customer
Address: 3 Test Lane, Example Town, Sample District 600002
Pho No: 9000000004
```

**Layout E: several copied orders inside one message.** Each inner order starts with `[day/month, time] Sender:` and has no year.

```
15/03/2025, 10:05 - Owner: [14/03, 22:36] Shop: Fourth Customer
1 Test Street
Sampleville
600003
9000000005
[15/03, 09:17] Shop: Fifth Customer
2 Test Street
Sampleville
600004
9000000006
1 cxe
```

## 4. Products

Real chats use many more product names than a short fixed list, with different spellings (for example a code, a full name or a shortened name).

So product names are **not written into the code**. The parser reads them from an **alias file**: a small table that maps every spelling to one `product_code`. It has the same layout as the `product_aliases` table.

| Environment | Alias file |
|---|---|
| Public | The fake file `data/synthetic/synthetic_product_aliases.csv` |
| Private | The owner's real file, kept in the private folder |

How the owner builds the real file:

1. Run the parser.
2. Open the review output. It lists every unknown product name with a count.
3. Add each name to the alias file with the right product code.
4. Run the parser again. Repeat until nothing is unknown.

Upper and lower case are treated as the same (`cxe` = `CXE`). An unknown name is never matched to the nearest product.

One spelling can mean only one product. If the file lists a spelling with two different product codes, the parser stops and names the spelling. A row with an alias but no code, or a code but no alias, also stops it. A completely empty row is skipped.

Product line formats:

- Prepaid: `1 cxe` means quantity 1, product CXE, no amount.
- COD: `1 cxe(900)` means quantity 1, product CXE, Rs 900 to collect for that line.

## 5. Parser workflow

1. **Export.** The owner exports each group chat (without media) and saves the text file in the private folder.
2. **Read.** The parser splits the file into messages. A new message starts at each line that begins with `DD/MM/YYYY, HH:MM - `.
3. **Split copied orders.** If a message contains lines starting with `[day/month, time] Sender:`, each one starts a separate order (layout E).
4. **Filter.** Each message is put into one of three groups (see section 6).
5. **Clean.** Small clean-ups that do not change meaning (see section 7).
6. **Extract.** Fields are found by their pattern, not by their position (see section 8).
7. **Payment type.** Set from the source group, then checked against payment words in the message.
8. **Validate.** The rules in section 10 are applied. A failed rule adds a flag.
9. **Output.** Clean orders, order items, a review queue with the reason for each flag, and a short summary of what was skipped.
10. **Manual review.** The owner looks through the review queue and fixes what can be fixed in the owner's own files: the alias file, the ignore list and the PIN code override file. Then the parser is run again.
11. **Load.** `sql/03_load_whatsapp_orders.sql` loads the orders into the private PostgreSQL database. Flagged orders are loaded together with their flags, so analysis can count them separately or leave them out. An order the tables cannot hold, such as one with an unknown product, is skipped and listed.

## 6. Filter rules

| Group | Rule | What happens |
|---|---|---|
| Skipped | System lines, `<Media omitted>` and similar, deleted messages, empty messages, messages that are only a link | Counted in the summary. Not kept |
| Order | The message has address lines and a PIN code or a phone number | Parsed. A missing PIN code or phone adds a flag |
| Other message | Everything else, such as notes, advert text and price lists | Counted in the summary. Not kept |

Two special cases:

- **Stock tally.** A message with only quantities and products (for example `20 cxe, 2 LP`) and no address is not an order. It is an "other message".
- **Ignore list.** Advert text can contain the owner's own phone number. The owner keeps a private list of numbers to ignore, so these messages are not mistaken for orders.

## 7. Clean-ups

These do not change the meaning of a message:

- Remove `<This message was edited>`.
- Remove `/-` after a product.
- Remove labels at the start of a line, such as `Name:`, `Address:`, `Pin code:` and `Phone:`.
- Remove extra spaces, empty lines and a dot after the name.
- Remove spaces inside a phone number or PIN code (`90000 00002`, `600 001`).
- Remove `+91` or a leading `0` from a phone number.
- Treat product names as the same in upper and lower case.

## 8. How fields are found

| Field | Rule |
|---|---|
| PIN code | A 6-digit number, not starting with 0. It can be on its own line or at the end of an address line |
| Phone | A 10-digit number starting with 6 to 9 |
| Second phone | If there are two phones, the first is the main phone. The second is kept in `notes` |
| Product line | At the end of the message: every comma-separated part is a quantity followed by a name |
| Payment word | A line that only says `COD` or `Prepaid`, in any letter case |
| Name | The first line |
| Address | All remaining lines |
| District and state | Looked up from the PIN code (see section 9). Not read from the address text |

## 9. District and state from the PIN code

The district is written in many ways in the address, and is sometimes missing. Reading it from the text is unreliable.

India Post publishes a public list that maps each PIN code to its district and state. The parser uses this list instead:

- The same district is always spelled the same way.
- If the PIN code is missing or not in the list, district and state stay unknown and the order is flagged.

**Owner's override file (optional).** The official list gives more than one district for some PIN codes, and misses a few. The parser never chooses for those. The owner can write the correct place in a private file with the columns `pin_code, district, state`, and pass it with `--pin-code-overrides`:

- A PIN code in the file uses the owner's district and state, even when the official list has a different one.
- The order gets the note `pin_code_override`, so it is always visible where the value came from.
- The file must be exact. A bad PIN code, an empty district or state, or the same PIN code with two places stops the script. A completely empty row is skipped.
- Names not used in the official list are printed as a spelling warning.
- The Shopify script takes the same file, so both channels use the same districts.
- The real file is private. `data/synthetic/synthetic_pin_code_overrides.csv` is a fake one for tests.

The list is a public dataset: the All India Pincode Directory from India Post. Its source and licence are recorded in `dataset_sources.md` (dataset 4). `python/prepare_pin_codes.py` reduces it to one row per PIN code.

## 10. Validation rules

A failed rule flags the order for manual review. The parser never guesses a value.

| Rule | Check |
|---|---|
| Phone | Present, 10 digits, starting with 6 to 9 |
| PIN code | Present, exactly 6 digits, not starting with 0, found in the PIN code list |
| More than one PIN code | Flagged. The parser does not choose between them |
| Required fields | Name, address, PIN code and phone |
| Quantity | Whole number, 1 or more |
| Product name | Must be in the alias file. Unknown names are flagged |
| COD without amount | A COD group order where no product has a bracket gets `cod_amount_missing` |
| COD with some amounts | A COD group order where only some products have a bracket gets `cod_amount_partial`. A bracket can hold the total for the whole order, so the amount stays unknown and is never estimated |
| Prepaid with amount | A Prepaid group order with an amount is flagged as a conflict |
| Payment conflict | If a payment word disagrees with the group, payment type is `needs_review` |
| Amount | A line amount below Rs 50 or above Rs 10,000 is flagged. The limits are settings that the owner can change |
| Duplicates | The same phone with the same products within 24 hours is flagged, not deleted |
| Unreadable order | Sent to review with the raw text |

### Default product rule

This is a business rule set by the owner, not a guess by the parser.

- If an order has no product line, it is treated as **1 cream (CXE)**.
- The order gets the note `product_defaulted_to_cxe`, so these orders can always be counted.
- This is the normal case, so it does **not** send the order to review by itself.
- If it is a COD order, the amount is also missing. The amount stays unknown and the order gets the flag `cod_amount_missing`.

## 11. Data fields

### Orders (one row per order)

| Field | Source | Notes |
|---|---|---|
| `order_id` | Generated | `W-` and a random code. Not made from the phone or the name |
| `order_datetime` | Export timestamp | When the order was **recorded** in the chat. The real order may be a day or two earlier |
| `sales_channel` | Parser | Always `whatsapp` |
| `source_group` | The group the chat file was exported from | `prepaid` or `cod` |
| `payment_type` | Group and payment words | `prepaid`, `cod` or `needs_review` |
| `customer_name` | Message | Private only |
| `phone` | Message | Private only. One phone number = one customer, across WhatsApp and Shopify |
| `address` | Message | Private only |
| `pin_code` | Message | Private only. Empty when the message has more than one |
| `district_city` | PIN code list, or the owner's override file | |
| `state` | PIN code list, or the owner's override file | |
| `order_amount` | Product lines | The amount to collect. Only for a COD order with an amount on every line. Otherwise empty |
| `amount_basis` | Parser | `cod_collectible` or `unknown` |
| `review_flags` | Parser | List of reasons, empty if clean |
| `notes` | Parser | For example `product_defaulted_to_cxe`, a second phone, or the inner time of a copied order |
| `source_line` | Export | The line number of the message in the chat file |

The original message text is written only to the review queue file, and only for flagged orders. It is private, and is kept to check the parser's work.

### Order items (one row per product line)

| Field | Example | Notes |
|---|---|---|
| `order_id` | (link) | Joins to the order |
| `product_code` | `CXE` | From the alias file. Stored in capitals. Empty when the name is unknown |
| `raw_name` | `cxe` | The name as written, in lower case |
| `quantity` | `1` | Whole number |
| `cod_collectible_amount` | `900` | COD only. The amount written in brackets after this product. Usually the total for the line. In an order where only some products have a bracket, it can be the total for the whole order, so that order is flagged. Empty for prepaid |
| `product_defaulted` | `true` | True when the order had no product line |

**Important:** `cod_collectible_amount` is the amount to be collected. It is not confirmed revenue.

## 12. What this data can and cannot show

Can show: number of orders, products, quantities, locations, dates recorded, payment type, and COD amounts to be collected.

Cannot show:

- **The exact order time**, because orders are often recorded in bulk later.
- **Prepaid order value**, because the amount is not recorded in WhatsApp.
- **Confirmed revenue**, because delivery, returns and money received are not marked.

Until other private sources are added (for example Delhivery COD remittance reports, Shopify orders or a price list), revenue is reported as **unknown**. Any estimate must be labelled as an estimate.

## 13. Privacy rules

- Real chat exports and parser outputs stay in the private folder `D:\Private\MarketPulse-Data\`, outside this Git project.
- Real customer data is never committed to GitHub.
- Real customer data is never uploaded or pasted into an external AI service, including coding assistants. This includes sample messages: describe the layout or make up an example instead.
- The parser is built and tested with fake messages only.
- The public portfolio contains the parser code, fake test messages and clearly labelled synthetic data.

## 14. Still to confirm

1. **COD amounts:** confirmed by the owner on 16 November 2026: a bracket usually belongs to its own product, but an order with several products sometimes has one bracket for the whole order. The parser cannot tell these two cases apart. So an order where only some products have a bracket keeps an unknown amount and is flagged. Still to decide: a rule or a manual step to settle these orders.
2. **Revenue sources:** which private records can confirm delivery and payment.
3. **PIN code list:** the source and the licence name are recorded in `dataset_sources.md`. The exact credit line that the licence requires is still to be recorded.
