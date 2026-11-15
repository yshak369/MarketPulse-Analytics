"""Turn the India Post PIN code directory into a small lookup list.

Input:  the "All India Pincode Directory" CSV from data.gov.in.
        It has one row per POST OFFICE, with these columns among others:
        pincode, district, statename.
Output: one row per PIN CODE, with the columns pin_code, district, state.
        This is the layout parse_whatsapp_orders.py reads with --pin-codes.

Source and licence: see docs/dataset_sources.md.

How to run (from the project folder):
    python python/prepare_pin_codes.py --input data/raw/<downloaded file>.csv --output data/processed/pin_codes.csv

Rule: nothing is guessed. If the post offices of one PIN code list
more than one district, the district is left empty for that PIN code.
The same goes for the state. The parser then flags such orders.
"""

import argparse

import pandas as pd

# Values the source file uses for "not available".
NOT_AVAILABLE = {"", "NA", "N/A", "NULL", "NAN"}


def clean_text(column):
    """Trim spaces, use capitals, and turn "not available" values into missing ones.

    The source mixes letter case ("Jagitial", "MANCHERIAL"), so capitals
    make the same district always look the same.
    """
    cleaned = column.astype(str).str.strip().str.upper().str.replace(r"\s+", " ", regex=True)
    return cleaned.mask(cleaned.isin(NOT_AVAILABLE))


def only_value(values):
    """Return the value if there is exactly one, otherwise an empty text."""
    distinct = values.dropna().unique()
    return distinct[0] if len(distinct) == 1 else ""


def build_lookup(post_offices):
    """Reduce the post office table to one row per PIN code."""
    table = pd.DataFrame(
        {
            "pin_code": post_offices["pincode"].astype(str).str.strip(),
            "district": clean_text(post_offices["district"]),
            "state": clean_text(post_offices["statename"]),
        }
    )
    # Keep only real PIN codes: 6 digits, not starting with 0.
    table = table[table["pin_code"].str.fullmatch(r"[1-9]\d{5}")]

    lookup = (
        table.groupby("pin_code")
        .agg(district=("district", only_value), state=("state", only_value))
        .reset_index()
        .sort_values("pin_code")
    )
    return lookup


def summarise(post_offices, lookup):
    """Print what was found, so the limits of the list are clear."""
    complete = (lookup["district"] != "") & (lookup["state"] != "")
    print(f"post office rows read:        {len(post_offices):>7}")
    print(f"PIN codes found:              {len(lookup):>7}")
    print(f"  district and state known:   {int(complete.sum()):>7}")
    print(f"  district left empty:        {int((lookup['district'] == '').sum()):>7}  (more than one district, or none given)")
    print(f"  state left empty:           {int((lookup['state'] == '').sum()):>7}  (more than one state, or none given)")
    print(f"districts: {lookup.loc[lookup['district'] != '', 'district'].nunique()}, "
          f"states and union territories: {lookup.loc[lookup['state'] != '', 'state'].nunique()}")


def main():
    arguments = argparse.ArgumentParser(description="Prepare the PIN code lookup list.")
    arguments.add_argument("--input", required=True, help="the downloaded India Post CSV file")
    arguments.add_argument("--output", required=True, help="where to write the lookup list")
    options = arguments.parse_args()

    # dtype=str keeps PIN codes as text. keep_default_na=False stops
    # Pandas from silently turning the text "NA" into a missing value.
    post_offices = pd.read_csv(options.input, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    lookup = build_lookup(post_offices)
    summarise(post_offices, lookup)

    lookup.to_csv(options.output, index=False, lineterminator="\n")
    print(f"written to {options.output}")


if __name__ == "__main__":
    main()
