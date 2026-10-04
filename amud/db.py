"""SQLite storage. One local file, no seed data."""

import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    business_name TEXT NOT NULL,
    address TEXT NOT NULL,
    company_number TEXT NOT NULL,
    company_number_label TEXT NOT NULL,
    phone TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT NOT NULL DEFAULT '',
    id_number TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    doc_type TEXT NOT NULL CHECK (doc_type IN ('quote', 'tax_invoice')),
    number INTEGER NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    issue_date TEXT NOT NULL,
    allocation_number TEXT,
    notes TEXT,
    vat_percent TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (doc_type, number)
);

CREATE TABLE IF NOT EXISTS line_items (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    description TEXT NOT NULL,
    quantity TEXT NOT NULL,
    unit_price TEXT NOT NULL
);
"""


def default_db_path() -> Path:
    root = Path(__file__).resolve().parent.parent
    return root / "data" / "amud.sqlite"


def get_db():
    if "db" not in g:
        path = Path(current_app.config["DATABASE"])
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_settings(db):
    return db.execute("SELECT * FROM settings WHERE id = 1").fetchone()


def next_number(db, doc_type: str) -> int:
    row = db.execute(
        "SELECT COALESCE(MAX(number), 0) + 1 AS n FROM documents WHERE doc_type = ?",
        (doc_type,),
    ).fetchone()
    return int(row["n"])
