# Private Setup Guide

This guide lists the steps and the exact commands for the **private environment**: the owner's real business data, on the owner's computer only.

It contains no private data. Every example value in it is fake.

The public environment (synthetic data) does not need this guide. See the README.

## 1. Three rules

1. **Real data stays outside the project folder**, in `D:\Private\MarketPulse-Data\`. The scripts refuse to write output inside the project, except under `data/processed/`, which Git ignores.
2. **Only counts leave the private folder.** Never copy order rows, names, phone numbers or addresses into a chat, an AI tool, an issue or a commit. Read an error message before sharing it. A database error can quote the values of the failing row, in lines that start with `DETAIL:` or `CONTEXT:`. Remove those lines first.
3. **The password file unlocks only the synthetic database.** Commands on `marketpulse_private` ask for the password every time. Keep it that way. A tool that runs commands on this computer then cannot open the real data by itself. When psql asks for the password, nothing appears while you type. That is normal.

## 2. The private folder

```
D:\Private\MarketPulse-Data\
    exports\                     files you download
        prepaid_chat.txt
        cod_chat.txt
        meta_campaigns.csv
        shopify_orders.csv
    reference\                   files you write and keep up to date
        products.csv
        product_aliases.csv
        ignore_phones.txt
        pin_code_overrides.csv   (optional)
    output\                      files the scripts write
        whatsapp\
        meta\
        shopify\
```

Use file and folder names without spaces. The load scripts need this.

## 3. One-time setup

### 3.1 Create the database

In pgAdmin, open the Query Tool on the `postgres` database and run:

```sql
CREATE DATABASE marketpulse_private OWNER marketpulse_user;
```

### 3.2 Create the tables

```
psql -U marketpulse_user -d marketpulse_private -h localhost -v ON_ERROR_STOP=1 -f sql/01_create_tables.sql
```

This is the same file the synthetic database uses, so both databases have the same eight tables.

### 3.3 Products

`reference\products.csv` has one row per product. It has the same layout as `data/synthetic/synthetic_products.csv`:

```
product_code,product_name,selling_price,unit_cost,cod_price
ABC,Example cream,100,40,120
```

- Write product codes in CAPITALS.
- `selling_price` is the normal **Prepaid** price. `cod_price` is the normal **COD** price.
- A price or cost you do not know can stay empty. Estimates that need it then stay unknown.

Load the file once:

```
psql -U marketpulse_user -d marketpulse_private -h localhost -c "\copy products (product_code, product_name, selling_price, unit_cost, cod_price) FROM 'D:/Private/MarketPulse-Data/reference/products.csv' WITH (FORMAT csv, HEADER true)"
```

To add a product later, add it to the file as your record, and add the one row to the table in pgAdmin (Query Tool on `marketpulse_private`):

```sql
INSERT INTO products (product_code, product_name, selling_price, unit_cost, cod_price)
VALUES ('XYZ', 'Example serum', 200, 80, 240);
```

### 3.3a Adding the COD price to a database built before November 2026

A database created before November 2026 has no `cod_price` column. Add it once:

```
psql -U marketpulse_user -d marketpulse_private -h localhost -f sql/06_add_cod_price.sql
```

It is safe to run again. Then add the `cod_price` column to `reference\products.csv`, and fill the prices in pgAdmin, one line per product (made-up values):

```sql
UPDATE products SET cod_price = 120 WHERE product_code = 'ABC';
```

Check that every product has one:

```sql
SELECT product_code FROM products WHERE cod_price IS NULL;
```

### 3.4 Alias file

`reference\product_aliases.csv` lists every way a product is written, with its code. It has the same layout as `data/synthetic/synthetic_product_aliases.csv`:

```
alias,source,product_code
abc,whatsapp,ABC
example cream 50g,shopify,ABC
```

- `alias` is the name as written in WhatsApp, or the product title in Shopify. Letter case and extra spaces do not matter.
- `source` is `whatsapp` or `shopify`.
- A name that is not in the file is flagged. It is never matched to a similar name.
- One spelling can have only one product code. If a spelling is listed with two different codes, the scripts stop and name it.
- Every `product_code` must also be in the `products` table. If not, its orders are skipped when loading.

### 3.5 Ignore list

`reference\ignore_phones.txt` holds the shop's own phone numbers, one per line. These numbers appear in advert text, and the parser must not read them as a customer's phone. A line that starts with `#` is a comment.

### 3.6 PIN code list

The parser looks up district and state in `data/processed/pin_codes.csv`. This file is made once from the official India Post file (see `dataset_sources.md`, dataset 4):

```
python python/prepare_pin_codes.py --input data/raw/<downloaded file>.csv --output data/processed/pin_codes.csv
```

### 3.7 PIN code overrides (optional)

The official list cannot decide the district of some PIN codes. For those, `reference\pin_code_overrides.csv` can hold the correct place:

```
pin_code,district,state
999999,EXAMPLE DISTRICT,EXAMPLE STATE
```

- Add only PIN codes you are sure about. Your file wins over the official list.
- Write the names in CAPITALS, spelled as the official list spells them.
- A bad PIN code, an empty district or state, or the same PIN code with two places stops the script.

## 4. Imports

Run every command from the project folder, in a terminal whose prompt starts with `(.venv)`. Each command is one line.

- The Python scripts accept normal Windows paths, such as `D:\Private\MarketPulse-Data\exports\prepaid_chat.txt`.
- The psql setting `-v input_folder=` needs forward slashes and no spaces, such as `D:/Private/MarketPulse-Data/output/whatsapp`.
- Use psql for the load scripts, not the pgAdmin Query Tool. The scripts use psql commands (lines that start with a backslash).
- The three imports can be run in any order.

### 4.1 WhatsApp orders

**Export.** In each WhatsApp group, choose Export chat, **without media**. Save the two text files as `exports\prepaid_chat.txt` and `exports\cod_chat.txt`. The parser reads the Android layout, where a message starts with `DD/MM/YYYY, HH:MM - Sender:`.

**Parse.**

```
python python/parse_whatsapp_orders.py --prepaid D:\Private\MarketPulse-Data\exports\prepaid_chat.txt --cod D:\Private\MarketPulse-Data\exports\cod_chat.txt --ignore-phones D:\Private\MarketPulse-Data\reference\ignore_phones.txt --aliases D:\Private\MarketPulse-Data\reference\product_aliases.csv --pin-codes data\processed\pin_codes.csv --pin-code-overrides D:\Private\MarketPulse-Data\reference\pin_code_overrides.csv --output D:\Private\MarketPulse-Data\output\whatsapp
```

Leave out `--pin-code-overrides` and its file if you have no override file.

The script prints counts only. It writes four files to `output\whatsapp\`:

| File | Contents |
|---|---|
| `whatsapp_orders.csv` | One row per order |
| `whatsapp_order_items.csv` | One row per product line |
| `whatsapp_review_queue.csv` | Every flagged order, with its flags and the original message |
| `whatsapp_unknown_products.csv` | Every product name that is not in the alias file, with a count |

**Review.**

1. Open `whatsapp_unknown_products.csv`. Add each name to the alias file with the right code. Run the parser again. Repeat until no unknown name is left.
2. Look through `whatsapp_review_queue.csv`.
3. To check the messages that were not read as orders, add `--details` to the end of the parse command. It lists every message with its line number and category, without the message text.

**Load.**

```
psql -U marketpulse_user -d marketpulse_private -h localhost -v schema=public -v input_folder=D:/Private/MarketPulse-Data/output/whatsapp -f sql/03_load_whatsapp_orders.sql
```

- Flagged orders are loaded together with their flags.
- An order the tables cannot hold is skipped and listed with the reason: an unknown or unreadable product, a quantity below 1, or a product that is not in the `products` table.
- Running the load again replaces all WhatsApp orders from earlier runs. Their order IDs are new each time.

### 4.2 Meta Ads

**Export.** In Meta Ads Manager, open the Campaigns table and choose the date range. Break the table down by day (Breakdown > By time > Day). Export the table as CSV and save it as `exports\meta_campaigns.csv`. Menu names in Ads Manager change over time.

The export needs these columns. The script lists any that are missing:

```
Reporting starts, Reporting ends, Campaign ID, Campaign name, Campaign delivery,
Attribution setting, Ad set budget, Ad set budget type, Ends, Amount spent (INR),
Impressions, Reach, Link clicks, Clicks (all), Landing page views, Results,
Result indicator
```

Export only the Campaigns table. The ad set and ad tables repeat the same spend, so loading them too would count it more than once.

**Prepare.**

```
python python/prepare_meta_ads.py --input D:\Private\MarketPulse-Data\exports\meta_campaigns.csv --output D:\Private\MarketPulse-Data\output\meta
```

**Load.**

```
psql -U marketpulse_user -d marketpulse_private -h localhost -v schema=public -v input_folder=D:/Private/MarketPulse-Data/output/meta -f sql/04_load_meta_ads.sql
```

The load is safe to run again. A campaign or a campaign-day that is already in the database is updated, and a new one is added. A later export that overlaps an older one creates no duplicates.

### 4.3 Shopify orders

**Export.** In the Shopify admin, go to Orders > Export and choose a plain CSV file. Save it as `exports\shopify_orders.csv`.

**Prepare.**

```
python python/prepare_shopify_orders.py --input D:\Private\MarketPulse-Data\exports\shopify_orders.csv --aliases D:\Private\MarketPulse-Data\reference\product_aliases.csv --pin-codes data\processed\pin_codes.csv --pin-code-overrides D:\Private\MarketPulse-Data\reference\pin_code_overrides.csv --output D:\Private\MarketPulse-Data\output\shopify
```

- The script prints the payment methods it found. The first time, check them against the rule: "Cash on Delivery" or the word "COD" means COD.
- `shopify_unknown_products.csv` lists product titles that are not in the alias file. Add them and run the script again.

**Load.**

```
psql -U marketpulse_user -d marketpulse_private -h localhost -v schema=public -v input_folder=D:/Private/MarketPulse-Data/output/shopify -f sql/05_load_shopify_orders.sql
```

The load is safe to run again. Shopify order numbers are fixed, so an order that is already in the database is updated and a new one is added.

## 5. Check the result

Run these in pgAdmin (Query Tool on `marketpulse_private`). They return counts only.

```sql
SELECT sales_channel, payment_type, count(*) AS orders, count(review_flags) AS flagged
FROM orders
GROUP BY sales_channel, payment_type
ORDER BY sales_channel, payment_type;

SELECT (SELECT count(*) FROM customers)      AS customers,
       (SELECT count(*) FROM order_items)    AS order_items,
       (SELECT count(*) FROM ad_campaigns)   AS campaigns,
       (SELECT count(*) FROM ad_performance) AS campaign_days;
```

## 6. If something goes wrong

| Message | Meaning | What to do |
|---|---|---|
| `Refusing to write output to ...` | The output folder is inside the project, where Git could pick it up | Use a folder under `D:\Private\MarketPulse-Data\output\` |
| `The export is missing these columns: ...` | The export was made without those columns | Add the columns in the export and download it again |
| `Alias file, row N: ...` | A row in the alias file is half empty, or one spelling has two product codes | Fix that row. The message says what is wrong |
| `Override file, row N: ...` | A row in the override file is unclear | Fix that row. The message says what is wrong |
| `Stopped: ...` | The script would have to guess | Read the message. It names the problem |
| A skipped order with `product_not_in_products_table` | A code in the alias file is not in the `products` table | Add the product (section 3.3), or correct the code in the alias file |
| `password authentication failed` | The password was typed wrongly. Typing is hidden | Run the command again |
| `Refusing to load ... into the public synthetic dataset` | The command named the synthetic database | Use `-d marketpulse_private` |
