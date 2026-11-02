"""GenAI Sports store MCP server (stdio).

Catalogue search, shopping list, store finder, delivery options and the full
order lifecycle as MCP tools. `user_email` parameters are overwritten by the ADK
agent's before_tool_callback with the signed-in user, so the LLM can never act on
someone else's account.

Inspect it standalone:
    npx @modelcontextprotocol/inspector python ecommerce_agent/mcp_server/store_server.py
"""
from __future__ import annotations

import functools
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import store_db as db  # noqa: E402

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations  # noqa: E402

DB_PATH = os.getenv("STORE_DB", str(Path(__file__).resolve().parents[1] / "data" / "store.db"))
READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

mcp = FastMCP("genai-sports-store")
conn = db.connect(DB_PATH)
_LOCK = threading.Lock()


def tool(annotations):
    """Register an MCP tool that runs under a lock and turns StoreError into a
    structured error the agent can explain to the shopper."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            with _LOCK:
                try:
                    return fn(*a, **kw)
                except db.StoreError as e:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    return {"status": "error", "error": str(e)}
        return mcp.tool(annotations=annotations)(wrapper)
    return deco


# ------------------------------------------------------------------ catalogue
@tool(READ)
def search_products(query: str, max_price: float | None = None, category: str = "", limit: int = 5) -> dict:
    """Find products matching a shopper's description (e.g. 'cushioned shoes for a
    first marathon'). Optional max_price (USD) and category filter."""
    return {"products": db.search(conn, query, max_price, category, max(1, min(limit, 10)))}


@tool(READ)
def search_products_by_brand(brand: str) -> dict:
    """List products for a brand name only (e.g. 'Nike', 'Hoka')."""
    rows = db.q(conn, """SELECT p.name, p.brand, p.category, p.description, MIN(v.price) AS price
                         FROM products p JOIN variants v USING (product_id)
                         WHERE lower(p.brand) LIKE lower(?) GROUP BY p.product_id
                         ORDER BY p.popularity DESC""", (f"%{brand.strip()}%",))
    return {"products": rows}


@tool(READ)
def get_product_details(product_name: str) -> dict:
    """Full details of one product: description, sizes, colours, price and total stock."""
    p = db.product(conn, product_name)
    v = db.q(conn, """SELECT v.size, v.color, v.price, COALESCE(SUM(i.quantity),0) AS stock
                      FROM variants v LEFT JOIN inventory i USING (variant_id)
                      WHERE v.product_id=? GROUP BY v.variant_id""", (p["product_id"],))
    return {"name": p["name"], "brand": p["brand"], "category": p["category"],
            "description": p["description"], "price": min(x["price"] for x in v),
            "sizes": sorted({x["size"] for x in v}), "colors": sorted({x["color"] for x in v}),
            "in_stock_variants": [x for x in v if x["stock"] > 0]}


@tool(READ)
def check_inventory(product_name: str, store_name: str = "") -> dict:
    """Units in stock per store (and per size/colour) for a product. Optionally one store."""
    p = db.product(conn, product_name)
    sql = """SELECT s.name AS store, v.size, v.color, i.quantity FROM inventory i
             JOIN variants v USING (variant_id) JOIN stores s USING (store_id)
             WHERE v.product_id=? AND i.quantity > 0"""
    args: tuple = (p["product_id"],)
    if store_name:
        sql += " AND s.store_id=?"
        args += (db.store(conn, store_name)["store_id"],)
    return {"product": p["name"], "availability": db.q(conn, sql + " ORDER BY s.name, v.size", args)}


# ------------------------------------------------------------------ shopping list
@tool(WRITE)
def add_to_shopping_list(user_email: str, product_name: str, size: str, color: str, quantity: int = 1) -> dict:
    """Add a product variant (exact size and colour) to the signed-in user's shopping list."""
    if not 1 <= quantity <= 10:
        raise db.StoreError("Quantity must be between 1 and 10.")
    u, p = db.user(conn, user_email), db.product(conn, product_name)
    v = db.variant(conn, p["product_id"], size, color)
    conn.execute("""INSERT INTO shopping_list_items (user_id, variant_id, quantity) VALUES (?,?,?)
                    ON CONFLICT (user_id, variant_id) DO UPDATE SET quantity = quantity + excluded.quantity""",
                 (u["user_id"], v["variant_id"], quantity))
    return {"status": "added", "product": p["name"], "size": v["size"], "color": v["color"],
            "unit_price": v["price"], "quantity": quantity}


@tool(WRITE)
def remove_from_shopping_list(user_email: str, product_name: str, size: str = "", color: str = "") -> dict:
    """Remove a product (optionally a specific size/colour) from the user's shopping list."""
    u, p = db.user(conn, user_email), db.product(conn, product_name)
    sql = """DELETE FROM shopping_list_items WHERE user_id=? AND variant_id IN
             (SELECT variant_id FROM variants WHERE product_id=?"""
    args: tuple = (u["user_id"], p["product_id"])
    if size:
        sql, args = sql + " AND lower(size)=lower(?)", args + (size,)
    if color:
        sql, args = sql + " AND lower(color)=lower(?)", args + (color,)
    n = conn.execute(sql + ")", args).rowcount
    return {"status": "removed" if n else "not_found", "items_removed": n}


@tool(READ)
def show_shopping_list(user_email: str) -> dict:
    """Show the signed-in user's shopping list with line totals and subtotal."""
    u = db.user(conn, user_email)
    items = db.q(conn, """SELECT p.name AS product, p.brand, p.category, v.size, v.color, v.price, s.quantity,
                          ROUND(v.price * s.quantity, 2) AS line_total
                          FROM shopping_list_items s JOIN variants v USING (variant_id)
                          JOIN products p USING (product_id) WHERE s.user_id=?""", (u["user_id"],))
    return {"user": u["name"], "items": items, "subtotal": round(sum(i["line_total"] for i in items), 2)}


# ------------------------------------------------------------------ stores & delivery
@tool(READ)
def find_nearby_stores(user_email: str, max_km: float = 80) -> dict:
    """Stores near the signed-in user's saved address, nearest first, with distance in km."""
    u = db.user(conn, user_email)
    stores = []
    for s in db.q(conn, "SELECT * FROM stores"):
        d = db.haversine_km(u["lat"], u["lon"], s["lat"], s["lon"])
        if d <= max_km:
            stores.append({"name": s["name"], "address": f"{s['address']}, {s['city']}",
                           "distance_km": round(d, 1), "lat": s["lat"], "lon": s["lon"]})
    return {"user_location": {"address": u["address"], "lat": u["lat"], "lon": u["lon"]},
            "stores": sorted(stores, key=lambda s: s["distance_km"])}


@tool(READ)
def list_delivery_methods(store_name: str) -> dict:
    """Delivery options (name, description, cost, ETA) offered by a store."""
    s = db.store(conn, store_name)
    return {"store": s["name"], "methods": db.q(conn,
            "SELECT name, description, cost, eta FROM delivery_methods WHERE store_id=?", (s["store_id"],))}


# ------------------------------------------------------------------ orders
def _delivery(store_id: int, method: str) -> dict:
    rows = db.q(conn, "SELECT * FROM delivery_methods WHERE store_id=? AND lower(name) LIKE lower(?)",
                (store_id, f"%{method.strip()}%"))
    if len(rows) != 1:
        raise db.StoreError(f"Delivery method {method!r} not offered by this store.")
    return rows[0]


@tool(DESTRUCTIVE)
def place_order(user_email: str, store_name: str, delivery_method: str) -> dict:
    """Place an order for everything in the user's shopping list, fulfilled by one store.
    Atomically checks and reserves stock, then empties the shopping list."""
    u, s = db.user(conn, user_email), db.store(conn, store_name)
    d = _delivery(s["store_id"], delivery_method)
    conn.execute("BEGIN IMMEDIATE")
    items = db.q(conn, """SELECT s.variant_id, s.quantity, v.price, p.name, v.size, v.color,
                          COALESCE(i.quantity, 0) AS stock
                          FROM shopping_list_items s JOIN variants v USING (variant_id)
                          JOIN products p USING (product_id)
                          LEFT JOIN inventory i ON i.variant_id = s.variant_id AND i.store_id = ?
                          WHERE s.user_id = ?""", (s["store_id"], u["user_id"]))
    if not items:
        raise db.StoreError("Shopping list is empty.")
    short = [f"{i['name']} ({i['size']}, {i['color']}): {i['stock']} in stock" for i in items if i["stock"] < i["quantity"]]
    if short:
        raise db.StoreError(f"Insufficient stock at {s['name']}: " + "; ".join(short)
                            + ". Try check_inventory to find another store.")
    subtotal = round(sum(i["price"] * i["quantity"] for i in items), 2)
    total = round(subtotal + d["cost"], 2)
    oid = conn.execute("""INSERT INTO orders (user_id, store_id, status, shipping_address, delivery_method_id,
                          shipping_cost, total_amount, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                       (u["user_id"], s["store_id"], "pending",
                        s["name"] if d["name"] == "Store Pickup" else u["address"],
                        d["delivery_method_id"], d["cost"], total, db.now())).lastrowid
    for i in items:
        conn.execute("INSERT INTO order_items (order_id, variant_id, quantity, price, product_name, details) "
                     "VALUES (?,?,?,?,?,?)", (oid, i["variant_id"], i["quantity"], i["price"], i["name"],
                                              f"Size {i['size']}, {i['color']}"))
        conn.execute("UPDATE inventory SET quantity = quantity - ? WHERE variant_id=? AND store_id=?",
                     (i["quantity"], i["variant_id"], s["store_id"]))
    conn.execute("DELETE FROM shopping_list_items WHERE user_id=?", (u["user_id"],))
    conn.execute("COMMIT")
    return {"status": "placed", "order_id": oid, "store": s["name"], "delivery_method": d["name"],
            "subtotal": subtotal, "shipping_cost": d["cost"], "total_amount": total, "eta": d["eta"]}


@tool(READ)
def check_order_status(user_email: str) -> dict:
    """All orders of the signed-in user with items, delivery method and status."""
    u = db.user(conn, user_email)
    orders = db.q(conn, """SELECT o.order_id, s.name AS store, o.status, o.total_amount, o.shipping_address,
                           d.name AS delivery_method, o.shipping_cost, o.created_at
                           FROM orders o JOIN stores s USING (store_id)
                           LEFT JOIN delivery_methods d ON d.delivery_method_id = o.delivery_method_id
                           WHERE o.user_id=? ORDER BY o.order_id DESC""", (u["user_id"],))
    for o in orders:
        o["items"] = db.q(conn, "SELECT product_name, details, quantity, price FROM order_items WHERE order_id=?",
                          (o["order_id"],))
    return {"user": u["name"], "orders": orders}


def _own_order(user_email: str, order_id: int) -> dict:
    u = db.user(conn, user_email)
    rows = db.q(conn, "SELECT * FROM orders WHERE order_id=? AND user_id=?", (order_id, u["user_id"]))
    if not rows:
        raise db.StoreError(f"Order #{order_id} not found for this user.")
    return rows[0]


@tool(WRITE)
def update_order_delivery_method(user_email: str, order_id: int, delivery_method: str) -> dict:
    """Change the delivery method of a pending order (total is recalculated)."""
    o = _own_order(user_email, order_id)
    if o["status"] != "pending":
        raise db.StoreError(f"Order #{order_id} is {o['status']}; only pending orders can be changed.")
    d = _delivery(o["store_id"], delivery_method)
    total = round(o["total_amount"] - o["shipping_cost"] + d["cost"], 2)
    conn.execute("UPDATE orders SET delivery_method_id=?, shipping_cost=?, total_amount=? WHERE order_id=?",
                 (d["delivery_method_id"], d["cost"], total, order_id))
    return {"status": "updated", "order_id": order_id, "delivery_method": d["name"], "total_amount": total}


@tool(DESTRUCTIVE)
def cancel_order(user_email: str, order_id: int) -> dict:
    """Cancel a pending order and return its items to store stock."""
    o = _own_order(user_email, order_id)
    if o["status"] != "pending":
        raise db.StoreError(f"Order #{order_id} is {o['status']} and cannot be cancelled.")
    conn.execute("BEGIN IMMEDIATE")
    for it in db.q(conn, "SELECT variant_id, quantity FROM order_items WHERE order_id=?", (order_id,)):
        conn.execute("UPDATE inventory SET quantity = quantity + ? WHERE variant_id=? AND store_id=?",
                     (it["quantity"], it["variant_id"], o["store_id"]))
    conn.execute("UPDATE orders SET status='cancelled' WHERE order_id=?", (order_id,))
    conn.execute("COMMIT")
    return {"status": "cancelled", "order_id": order_id}


if __name__ == "__main__":
    mcp.run()
