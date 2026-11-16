"""Connect Python to a MarketPulse PostgreSQL database.

pandas reads database tables through two packages:
  * SQLAlchemy: the library pandas uses to talk to a SQL database.
  * psycopg2:   the driver that speaks PostgreSQL's own language.

How to check a connection (from the project folder):
    python python/database.py --database marketpulse_synthetic

It prints the number of rows in each table. Counts only, so the output
is safe to share, also for the private database.

Passwords:
  * No password is written in this project, saved to a file or printed.
  * For marketpulse_synthetic, PostgreSQL itself finds the password in
    the owner's password file (pgpass.conf), exactly as psql does.
  * A database that is not in the password file, such as
    marketpulse_private, makes this script ask for the password.
    Nothing appears while you type. That is normal.

Safety: a connection is READ-ONLY unless the caller asks otherwise.
The database then refuses every change. So code that should only look
at the data cannot change it by mistake.
"""

import argparse
import getpass
import os
import sys

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

# The project's own database login. It owns only the MarketPulse databases.
USER = "marketpulse_user"
HOST = "localhost"
PORT = 5432

SYNTHETIC_DATABASE = "marketpulse_synthetic"

# The eight tables of docs/schema_design.md.
TABLE_NAMES = [
    "products", "product_aliases", "customers", "orders", "order_items",
    "shipments", "ad_campaigns", "ad_performance",
]


class ConnectionProblem(Exception):
    """The database could not be opened. The message says why."""


def kind_of_data(database):
    """Say what kind of data a database holds, so every output is labelled."""
    if database == SYNTHETIC_DATABASE:
        return "SYNTHETIC (fake) data"
    return "PRIVATE data: share counts only, never rows"


def build_engine(database, password, read_only):
    """Make the SQLAlchemy "engine": the object pandas uses to reach the database."""
    url = URL.create("postgresql+psycopg2", username=USER, password=password,
                     host=HOST, port=PORT, database=database)
    # This setting makes the database itself refuse every change.
    settings = {"options": "-c default_transaction_read_only=on"} if read_only else {}
    return create_engine(url, connect_args=settings)


def try_to_open(engine):
    """Return None when the database opens, otherwise the reason it did not."""
    try:
        with engine.connect():
            return None
    except SQLAlchemyError as error:
        engine.dispose()
        # The first line is the reason. The rest is technical detail.
        return str(getattr(error, "orig", error)).strip().split("\n")[0]


def a_person_can_type():
    """True when the script runs in a real terminal, with a keyboard.

    Python's own check (isatty) is not enough on Windows. When no
    keyboard is attached, it can still answer True, and the script
    would then wait for a password for ever. So on Windows the system
    itself is asked whether the input is a real console.
    """
    if sys.stdin is None or not sys.stdin.isatty():
        return False
    if os.name != "nt":
        return True
    import ctypes   # these two modules exist on Windows only
    import msvcrt
    console_mode = ctypes.c_ulong()
    handle = msvcrt.get_osfhandle(sys.stdin.fileno())
    return bool(ctypes.windll.kernel32.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(console_mode)))


def connect(database, read_only=True, ask_password=True):
    """Open a database and return its engine.

    First try without a password: PostgreSQL then looks in the owner's
    password file. If the database is not listed there, ask for the
    password with hidden typing. The password is kept in memory only.

    read_only=True  the database refuses every change (the default).
    ask_password=False  never ask; raise ConnectionProblem instead.
    """
    engine = build_engine(database, None, read_only)
    problem = try_to_open(engine)
    if problem is None:
        return engine

    if "no password supplied" not in problem:
        raise ConnectionProblem(f"Could not open {database}: {problem}")
    if not ask_password or not a_person_can_type():
        raise ConnectionProblem(
            f"Could not open {database}: it is not in the password file, "
            "and a password cannot be asked for here."
        )

    password = getpass.getpass(f"Password for {USER} on {database} (nothing appears while you type): ")
    engine = build_engine(database, password, read_only)
    problem = try_to_open(engine)
    if problem is not None:
        raise ConnectionProblem(f"Could not open {database}: {problem}")
    return engine


def read_table(engine, table, schema="public"):
    """Read one whole table into a pandas DataFrame (a table held in memory)."""
    return pd.read_sql_table(table, engine, schema=schema)


def read_tables(engine, schema="public"):
    """Read the eight tables. Returns a dictionary: table name -> DataFrame."""
    return {name: read_table(engine, name, schema) for name in TABLE_NAMES}


def main():
    arguments = argparse.ArgumentParser(description="Check the connection to a MarketPulse database.")
    arguments.add_argument("--database", required=True, help="for example marketpulse_synthetic")
    arguments.add_argument("--schema", default="public", help="schema to read (default: public)")
    options = arguments.parse_args()

    try:
        engine = connect(options.database)
    except ConnectionProblem as problem:
        raise SystemExit(str(problem))

    with engine.connect() as connection:
        read_only = connection.execute(text("SHOW default_transaction_read_only")).scalar()
    print(f"connected to {options.database} as {USER}")
    print(f"  {kind_of_data(options.database)}")
    print(f"  read-only: {read_only}")

    try:
        tables = read_tables(engine, options.schema)
    except ValueError as problem:
        raise SystemExit(f"Could not read schema '{options.schema}': {problem}")
    finally:
        engine.dispose()

    print(f"tables in schema '{options.schema}':")
    for name, table in tables.items():
        print(f"  {name:<16} {len(table):>6} rows, {len(table.columns):>2} columns")


if __name__ == "__main__":
    main()
