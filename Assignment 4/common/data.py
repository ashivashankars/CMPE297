"""The one business scenario every codelab renders: Q3 sales for a coffee chain.

Keeping the data identical across A2UI, AG-UI, MCP Apps, json-render, OpenUI and
the harness lets you compare *formats and transports*, not content.
"""

import csv
from pathlib import Path

CSV = Path(__file__).parent / "fixtures" / "sales_q3.csv"


def rows():
    with CSV.open(newline="") as f:
        return [{**r, "revenue": int(r["revenue"]), "orders": int(r["orders"])} for r in csv.DictReader(f)]


def by_region():
    """[{region, revenue, orders}] for the quarter, largest first."""
    totals = {}
    for r in rows():
        t = totals.setdefault(r["region"], {"region": r["region"], "revenue": 0, "orders": 0})
        t["revenue"] += r["revenue"]
        t["orders"] += r["orders"]
    return sorted(totals.values(), key=lambda t: -t["revenue"])


def summary():
    regions = by_region()
    revenue = sum(r["revenue"] for r in regions)
    orders = sum(r["orders"] for r in regions)
    return {
        "quarter": "Q3 2026",
        "revenue": revenue,
        "orders": orders,
        "avg_ticket": round(revenue / orders, 2),
        "growth": "+12%",
        "regions": regions,
    }


def region_detail(region):
    """Monthly revenue for one region: the drill-down every 'View details' button asks for."""
    months = [r for r in rows() if r["region"].lower() == str(region).lower()]
    if not months:
        raise KeyError(f"unknown region {region!r}; known: {[r['region'] for r in by_region()]}")
    return {
        "region": months[0]["region"],
        "months": [m["month"] for m in months],
        "revenue": [m["revenue"] for m in months],
        "orders": [m["orders"] for m in months],
        "total": sum(m["revenue"] for m in months),
    }


def money(n):
    return f"${n/1_000_000:.2f}M" if n >= 1_000_000 else f"${n/1000:.0f}K"
