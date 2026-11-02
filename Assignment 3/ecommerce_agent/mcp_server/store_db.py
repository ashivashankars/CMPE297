"""SQLite implementation of the GenAI Sports store. The production version of the
same queries runs on AlloyDB through MCP Toolbox (deployment/toolbox/tools.yaml)."""
from __future__ import annotations

import math
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import store_seed as seed

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE,
    address TEXT, lat REAL, lon REAL);
CREATE TABLE IF NOT EXISTS products (product_id INTEGER PRIMARY KEY, name TEXT UNIQUE, brand TEXT,
    category TEXT, description TEXT, popularity REAL);
CREATE TABLE IF NOT EXISTS variants (variant_id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products,
    size TEXT, color TEXT, price REAL);
CREATE TABLE IF NOT EXISTS stores (store_id INTEGER PRIMARY KEY, name TEXT UNIQUE, address TEXT, city TEXT,
    lat REAL, lon REAL);
CREATE TABLE IF NOT EXISTS inventory (variant_id INTEGER REFERENCES variants, store_id INTEGER REFERENCES stores,
    quantity INTEGER CHECK (quantity >= 0), PRIMARY KEY (variant_id, store_id));
CREATE TABLE IF NOT EXISTS delivery_methods (delivery_method_id INTEGER PRIMARY KEY, store_id INTEGER REFERENCES stores,
    name TEXT, description TEXT, cost REAL, eta TEXT);
CREATE TABLE IF NOT EXISTS shopping_list_items (item_id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users,
    variant_id INTEGER REFERENCES variants, quantity INTEGER CHECK (quantity > 0), UNIQUE (user_id, variant_id));
CREATE TABLE IF NOT EXISTS orders (order_id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users,
    store_id INTEGER REFERENCES stores, status TEXT, shipping_address TEXT, delivery_method_id INTEGER,
    shipping_cost REAL, total_amount REAL, created_at TEXT);
CREATE TABLE IF NOT EXISTS order_items (order_item_id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders,
    variant_id INTEGER, quantity INTEGER, price REAL, product_name TEXT, details TEXT);
"""


class StoreError(Exception):
    """Business-rule violation reported back to the agent as a tool error."""


def connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # several MCP server processes may share the file
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        _seed(conn)
    return conn


def _seed(conn):
    conn.execute("BEGIN")
    conn.executemany("INSERT INTO users (name,email,address,lat,lon) VALUES (?,?,?,?,?)", seed.USERS)
    conn.executemany("INSERT INTO stores (name,address,city,lat,lon) VALUES (?,?,?,?,?)", seed.STORES)
    store_ids = [r[0] for r in conn.execute("SELECT store_id FROM stores")]
    for sid in store_ids:
        conn.executemany("INSERT INTO delivery_methods (store_id,name,description,cost,eta) VALUES (?,?,?,?,?)",
                         [(sid, *d) for d in seed.DELIVERY])
    for pi, (name, brand, cat, desc, pop, sizes, colors, price) in enumerate(seed.PRODUCTS):
        pid = conn.execute("INSERT INTO products (name,brand,category,description,popularity) VALUES (?,?,?,?,?)",
                           (name, brand, cat, desc, pop)).lastrowid
        for si, size in enumerate(sizes):
            for ci, color in enumerate(colors):
                vid = conn.execute("INSERT INTO variants (product_id,size,color,price) VALUES (?,?,?,?)",
                                   (pid, size, color, price)).lastrowid
                for k, sid in enumerate(store_ids):
                    qty = (pi * 7 + si * 3 + ci * 5 + k * 11) % 9   # deterministic, some zero stock
                    conn.execute("INSERT INTO inventory VALUES (?,?,?)", (vid, sid, qty))
    conn.execute("COMMIT")


def q(conn, sql, args=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def user(conn, email: str) -> dict:
    rows = q(conn, "SELECT * FROM users WHERE lower(email)=lower(?)", (email,))
    if not rows:
        raise StoreError("Unknown user. Please sign in.")
    return rows[0]


def product(conn, name: str) -> dict:
    rows = q(conn, "SELECT * FROM products WHERE lower(name)=lower(?)", (name.strip(),))
    if not rows:
        rows = q(conn, "SELECT * FROM products WHERE lower(name) LIKE lower(?) ORDER BY popularity DESC",
                 (f"%{name.strip()}%",))
    if not rows:
        raise StoreError(f"No product named {name!r}.")
    return rows[0]


def store(conn, name: str) -> dict:
    rows = q(conn, "SELECT * FROM stores WHERE lower(name) LIKE lower(?)", (f"%{name.strip()}%",))
    if len(rows) != 1:
        raise StoreError(f"Store {name!r} not found or ambiguous. Use find_nearby_stores.")
    return rows[0]


def variant(conn, product_id: int, size: str, color: str) -> dict:
    rows = q(conn, "SELECT * FROM variants WHERE product_id=? AND lower(size)=lower(?) AND lower(color)=lower(?)",
             (product_id, size.strip(), color.strip()))
    if not rows:
        opts = q(conn, "SELECT size, color FROM variants WHERE product_id=?", (product_id,))
        raise StoreError(f"Variant size={size!r} color={color!r} not available. Options: "
                         f"sizes {sorted({o['size'] for o in opts})}, colors {sorted({o['color'] for o in opts})}")
    return rows[0]


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _terms(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1}


def search(conn, query: str, max_price: float | None = None, category: str = "", limit: int = 5) -> list[dict]:
    """Keyword relevance - each query term scores the best field it hits
    (name/brand 3, category 2, description 1) - plus popularity as a tie-breaker.
    A local stand-in for the AlloyDB vector + full-text search in production."""
    words = _terms(query) - {"for", "the", "and", "with", "my", "want", "need", "looking"}
    prods = q(conn, """SELECT p.*, MIN(v.price) AS price FROM products p JOIN variants v USING (product_id)
                       GROUP BY p.product_id""")
    scored = []
    for p in prods:
        if max_price is not None and p["price"] > max_price:
            continue
        if category and category.lower() not in p["category"].lower():
            continue
        fields = ((3, _terms(f"{p['name']} {p['brand']}")), (2, _terms(p["category"])),
                  (1, _terms(p["description"])))
        score = sum(max((wt for wt, terms in fields if w in terms), default=0) for w in words)
        if score or not words:
            scored.append((score + p["popularity"], p))
    scored.sort(key=lambda t: -t[0])
    return [{k: p[k] for k in ("name", "brand", "category", "description", "price")} for _, p in scored[:limit]]


def haversine_km(a_lat, a_lon, b_lat, b_lon) -> float:
    r = 6371.0
    dlat, dlon = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a_lat)) * math.cos(math.radians(b_lat)) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
