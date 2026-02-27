"""Generate rich demo data for dashboard testing.

Creates 30 days of realistic snapshot history, volume patterns, findings trends,
cost/usage data, and expanded dbt results so every dashboard page has meaningful content.

Usage:
    Called from demo_dashboard.py — not intended for standalone use.
"""

from __future__ import annotations

import json
import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from olly.config import OllyConfig
from olly.models import (
    ColumnInfo,
    CostRecord,
    TableInfo,
    VolumeRecord,
)
from olly.state import StateDB, get_olly_dir

DEV_DIR = Path(__file__).resolve().parent
DB_PATH = DEV_DIR / "warehouse.duckdb"
DBT_TARGET_DIR = DEV_DIR / "target"

# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------

# (table_name, table_type, columns_as_list_of_(name, type, nullable))
# Types use Ibis-style names (what DuckDB adapter reports via str(ibis_type)):
#   INTEGER -> int32, VARCHAR -> string, DOUBLE -> float64,
#   TIMESTAMP -> timestamp(6), BIGINT -> int64, BOOLEAN -> boolean
# These are the columns for the "final" schema. Evolution events modify earlier snapshots.
TABLE_DEFS: list[tuple[str, str, list[tuple[str, str, bool]]]] = [
    (
        "orders",
        "TABLE",
        [
            ("id", "int32", True),
            ("customer_id", "int32", True),
            ("amount", "float64", True),
            ("created_at", "timestamp(6)", True),
            ("updated_at", "timestamp(6)", True),
            ("status", "string", True),
        ],
    ),
    (
        "customers",
        "TABLE",
        [
            ("id", "int32", True),
            ("name", "string", True),
            ("email", "string", True),
        ],
    ),
    (
        "products",
        "TABLE",
        [
            ("id", "int32", True),
            ("name", "string", True),
            ("price", "float64", True),
        ],
    ),
    (
        "payments",
        "TABLE",
        [
            ("id", "int32", True),
            ("order_id", "int32", True),
            ("method", "string", True),
            ("amount", "float64", True),
            ("paid_at", "timestamp(6)", True),
        ],
    ),
    (
        "shipments",
        "TABLE",
        [
            ("id", "int32", True),
            ("order_id", "int32", True),
            ("carrier", "string", True),
            ("shipped_at", "timestamp(6)", True),
            ("delivered_at", "timestamp(6)", True),
        ],
    ),
    (
        "returns",
        "TABLE",
        [
            ("id", "int32", True),
            ("order_id", "int32", True),
            ("reason", "string", True),
            ("created_at", "timestamp(6)", True),
        ],
    ),
    (
        "reviews",
        "TABLE",
        [
            ("id", "int32", True),
            ("customer_id", "int32", True),
            ("product_id", "int32", True),
            ("rating", "int32", True),
            ("body", "string", True),
            ("created_at", "timestamp(6)", True),
        ],
    ),
    (
        "inventory",
        "TABLE",
        [
            ("id", "int32", True),
            ("product_id", "int32", True),
            ("warehouse", "string", True),
            ("quantity", "int32", True),
            ("updated_at", "timestamp(6)", True),
        ],
    ),
    (
        "suppliers",
        "TABLE",
        [
            ("id", "int32", True),
            ("name", "string", True),
            ("contact_email", "string", True),
            ("country", "string", True),
        ],
    ),
    (
        "categories",
        "TABLE",
        [
            ("id", "int32", True),
            ("name", "string", True),
            ("parent_id", "int32", True),
        ],
    ),
    (
        "order_items",
        "TABLE",
        [
            ("id", "int32", True),
            ("order_id", "int32", True),
            ("product_id", "int32", True),
            ("quantity", "int32", True),
            ("unit_price", "float64", True),
        ],
    ),
    (
        "customer_sessions",
        "TABLE",
        [
            ("id", "int32", True),
            ("customer_id", "int32", True),
            ("started_at", "timestamp(6)", True),
            ("ended_at", "timestamp(6)", True),
            ("page_views", "int32", True),
            ("device", "string", True),
        ],
    ),
    # Views
    (
        "order_summary",
        "VIEW",
        [
            ("customer_id", "int32", True),
            ("order_count", "int64", True),
            ("total_amount", "float64", True),
        ],
    ),
    (
        "monthly_revenue",
        "VIEW",
        [
            ("month", "string", True),
            ("revenue", "float64", True),
            ("order_count", "int64", True),
        ],
    ),
    (
        "customer_lifetime_value",
        "VIEW",
        [
            ("customer_id", "int32", True),
            ("name", "string", True),
            ("total_spent", "float64", True),
            ("order_count", "int64", True),
            ("first_order", "timestamp(6)", True),
        ],
    ),
]

SCHEMA_NAME = "main"

# Volume profiles: (start_count, growth_rate_per_30d, pattern_type)
# pattern_type: "growth", "seasonal", "stable", "volatile"
VOLUME_PROFILES: dict[str, tuple[int, float, str]] = {
    "orders": (800, 0.6, "growth"),
    "customers": (200, 0.3, "growth"),
    "products": (150, 0.15, "stable"),
    "payments": (750, 0.55, "growth"),
    "shipments": (600, 0.45, "growth"),
    "returns": (50, 0.4, "growth"),
    "reviews": (300, 0.5, "seasonal"),
    "inventory": (400, 0.1, "volatile"),
    "suppliers": (25, 0.05, "stable"),
    "categories": (20, 0.0, "stable"),
    "order_items": (2000, 0.65, "growth"),
    "customer_sessions": (5000, 0.7, "seasonal"),
}

# Users for cost data
USERS = [
    "alice@company.com",
    "bob@company.com",
    "carol@company.com",
    "dave@company.com",
    "eve@company.com",
    "frank@company.com",
]

# Cost tiers: (queries_per_day_range, cost_per_query_range)
COST_TIERS: dict[str, tuple[tuple[int, int], tuple[float, float]]] = {
    "orders": ((150, 400), (0.05, 0.20)),
    "customer_sessions": ((200, 500), (0.08, 0.25)),
    "order_items": ((100, 350), (0.06, 0.18)),
    "customers": ((50, 150), (0.02, 0.08)),
    "payments": ((40, 120), (0.03, 0.10)),
    "shipments": ((30, 100), (0.02, 0.07)),
    "reviews": ((20, 80), (0.01, 0.05)),
    "products": ((15, 60), (0.01, 0.04)),
    "returns": ((10, 40), (0.01, 0.03)),
    "inventory": ((5, 20), (0.005, 0.02)),
    "suppliers": ((1, 5), (0.001, 0.005)),
    "categories": ((0, 3), (0.001, 0.003)),
}


# ---------------------------------------------------------------------------
# Schema evolution
# ---------------------------------------------------------------------------


def _get_table_schema_at_day(day: int) -> list[TableInfo]:
    """Return the table schemas as they should appear on a given day (0-29).

    Evolution events create visible diffs between adjacent snapshots.
    The final snapshot (day 29) must match the pre-drift warehouse state so that
    drift() produces meaningful schema diffs in the live check:
      - orders does NOT have 'status' (drift adds it)
      - returns table does NOT exist (drift creates it)
      - customers HAS 'email' (drift drops it)
      - products.price is float64 (drift changes it to string)
    """
    tables = []
    for tname, ttype, columns in TABLE_DEFS:
        # reviews table appears on day 12
        if tname == "reviews" and day < 12:
            continue

        # returns table appears days 15-24, then disappears before drift re-creates it
        if tname == "returns" and (day < 15 or day >= 25):
            continue

        cols = list(columns)

        # orders.status: appears days 10-22, then removed before drift re-adds it
        if tname == "orders" and (day < 10 or day >= 23):
            cols = [(n, t, nu) for n, t, nu in cols if n != "status"]

        # customers.email: dropped days 18-22 (a past incident), restored by day 23
        if tname == "customers" and 18 <= day < 23:
            cols = [(n, t, nu) for n, t, nu in cols if n != "email"]

        # products.price type change days 20-25 (float64 → string), reverted by day 26
        if tname == "products" and 20 <= day < 26:
            cols = [
                (n, "string" if n == "price" else t, nu) for n, t, nu in cols
            ]

        table_info = TableInfo(
            schema_name=SCHEMA_NAME,
            table_name=tname,
            table_type=ttype,
            columns=[ColumnInfo(n, t, nu) for n, t, nu in cols],
        )
        tables.append(table_info)
    return tables


# ---------------------------------------------------------------------------
# Volume generation
# ---------------------------------------------------------------------------


def _compute_row_count(table_name: str, day: int, day_of_week: int) -> int:
    """Compute a realistic row count for a table on a given day."""
    if table_name not in VOLUME_PROFILES:
        return 0  # views
    start, growth_rate, pattern = VOLUME_PROFILES[table_name]

    # Base growth curve
    base = start * (1 + growth_rate) ** (day / 30)

    if pattern == "growth":
        # Weekend dip for transactional tables
        weekday_factor = 0.82 if day_of_week >= 5 else 1.0
        noise = random.uniform(0.96, 1.04)
        return max(1, int(base * weekday_factor * noise))

    if pattern == "seasonal":
        # Sine wave for sessions/reviews (weekly cycle)
        seasonal = 1.0 + 0.15 * math.sin(2 * math.pi * day / 7)
        weekday_factor = 0.75 if day_of_week >= 5 else 1.0
        noise = random.uniform(0.93, 1.07)
        return max(1, int(base * seasonal * weekday_factor * noise))

    if pattern == "stable":
        noise = random.uniform(0.97, 1.03)
        return max(1, int(base * noise))

    if pattern == "volatile":
        # Random swings for inventory
        swing = random.uniform(0.7, 1.3)
        return max(1, int(base * swing))

    return max(1, int(base))


# ---------------------------------------------------------------------------
# Findings generation
# ---------------------------------------------------------------------------

_FINDING_TEMPLATES: list[tuple[str, str, str, str]] = [
    ("schema", "warning", "orders", "Column 'discount_code' added"),
    ("schema", "warning", "customers", "Column 'phone' added"),
    ("schema", "error", "products", "Column 'price' type changed from DOUBLE to VARCHAR"),
    ("schema", "warning", "payments", "New table 'payment_refunds' detected"),
    ("schema", "error", "customers", "Column 'email' removed"),
    ("volume", "error", "orders", "Row count anomaly: z-score 3.2 (expected ~{expected}, got {actual})"),
    ("volume", "warning", "customer_sessions", "Row count anomaly: z-score 2.1 (expected ~{expected}, got {actual})"),
    ("volume", "error", "order_items", "Row count anomaly: z-score 4.5 (expected ~{expected}, got {actual})"),
    ("volume", "warning", "inventory", "Row count anomaly: z-score 2.8 (expected ~{expected}, got {actual})"),
    ("freshness", "error", "orders", "Table stale: last updated 52 hours ago (threshold: 24h)"),
    ("freshness", "warning", "shipments", "Table approaching staleness: last updated 20 hours ago"),
    ("freshness", "error", "payments", "Table stale: last updated 48 hours ago (threshold: 24h)"),
    ("freshness", "warning", "reviews", "Table approaching staleness: last updated 22 hours ago"),
    ("contracts", "error", "products", "Column 'price' expected type float, got VARCHAR"),
    ("contracts", "error", "customers", "Missing required column 'email'"),
    ("contracts", "warning", "orders", "Column 'status' not in contract definition"),
    ("integrity", "error", "shipments", "COUNT mismatch: source=500, target=487 (delta=13)"),
    ("integrity", "warning", "payments", "COUNT mismatch: source=750, target=748 (delta=2, within tolerance)"),
]


def _generate_findings_for_day(day: int) -> list[dict]:
    """Generate a set of findings appropriate for a given day in the timeline."""
    # Ramp up findings over time
    if day < 8:
        max_findings = random.randint(0, 1)
    elif day < 15:
        max_findings = random.randint(1, 4)
    elif day < 22:
        max_findings = random.randint(4, 10)
    elif day < 27:
        max_findings = random.randint(6, 12)
    else:
        max_findings = random.randint(3, 8)

    if max_findings == 0:
        return []

    # Pick a subset of templates
    available = list(_FINDING_TEMPLATES)
    # Only schema evolution findings after the evolution day
    if day < 15:
        available = [f for f in available if not (f[2] == "orders" and "status" in f[3])]
    if day < 20:
        available = [f for f in available if f[2] != "reviews"]
    if day < 25:
        available = [f for f in available if not (f[2] == "customers" and "email" in f[3].lower() and "removed" in f[3].lower())]
    if day < 28:
        available = [f for f in available if not (f[2] == "products" and "VARCHAR" in f[3])]

    count = min(max_findings, len(available))
    chosen = random.sample(available, count)

    findings = []
    for check_type, severity, table, desc in chosen:
        # Fill in volume placeholders
        if "{expected}" in desc:
            expected = random.randint(500, 5000)
            actual = expected + random.randint(200, 2000) * random.choice([-1, 1])
            desc = desc.format(expected=expected, actual=max(0, actual))
        findings.append({
            "check_type": check_type,
            "severity": severity,
            "schema_name": SCHEMA_NAME,
            "table_name": table,
            "description": desc,
            "connection_name": "primary",
        })
    return findings


# ---------------------------------------------------------------------------
# Cost data generation
# ---------------------------------------------------------------------------


def _generate_cost_records(tables: list[str]) -> list[CostRecord]:
    """Generate cost records for one cost run."""
    records = []
    for table in tables:
        if table not in COST_TIERS:
            continue
        (q_lo, q_hi), (c_lo, c_hi) = COST_TIERS[table]
        # Distribute across 2-4 users
        num_users = random.randint(1, min(4, len(USERS)))
        chosen_users = random.sample(USERS, num_users)
        total_queries = random.randint(q_lo, max(q_lo, q_hi))
        for user in chosen_users:
            user_queries = max(1, total_queries // num_users + random.randint(-5, 5))
            cost_per_q = random.uniform(c_lo, c_hi)
            cost = round(user_queries * cost_per_q, 4)
            bytes_billed = int(cost * 1e9 / 5.0)  # ~$5/TB
            records.append(CostRecord(
                schema_name=SCHEMA_NAME,
                table_name=table,
                user_email=user,
                total_bytes_billed=bytes_billed,
                estimated_cost_usd=cost,
                query_count=user_queries,
            ))
    return records


# ---------------------------------------------------------------------------
# Expanded dbt results
# ---------------------------------------------------------------------------


def _write_expanded_dbt_results() -> None:
    """Write an expanded dbt run_results.json with ~25 results."""
    DBT_TARGET_DIR.mkdir(exist_ok=True)
    invocation_id = str(uuid.uuid4())

    results = [
        # Models — 12 total
        {
            "unique_id": "model.shop.stg_orders",
            "status": "success",
            "execution_time": 1.23,
            "message": "OK created sql table model main.stg_orders",
            "compiled_code": "SELECT id AS order_id, customer_id, amount, created_at, updated_at FROM main.raw_orders",
        },
        {
            "unique_id": "model.shop.stg_customers",
            "status": "success",
            "execution_time": 0.87,
            "message": "OK created sql table model main.stg_customers",
            "compiled_code": "SELECT id AS customer_id, name, email FROM main.raw_customers",
        },
        {
            "unique_id": "model.shop.stg_payments",
            "status": "error",
            "execution_time": 0.45,
            "message": "Compilation Error: column 'payment_method' does not exist",
            "compiled_code": "SELECT id AS payment_id, order_id, payment_method, amount FROM main.raw_payments",
        },
        {
            "unique_id": "model.shop.stg_products",
            "status": "success",
            "execution_time": 0.65,
            "message": "OK created sql table model main.stg_products",
            "compiled_code": "SELECT id AS product_id, name, price, category_id FROM main.raw_products",
        },
        {
            "unique_id": "model.shop.stg_shipments",
            "status": "success",
            "execution_time": 0.92,
            "message": "OK created sql table model main.stg_shipments",
            "compiled_code": "SELECT id, order_id, carrier, shipped_at, delivered_at FROM main.raw_shipments",
        },
        {
            "unique_id": "model.shop.fct_orders",
            "status": "success",
            "execution_time": 142.3,
            "message": "OK created sql table model main.fct_orders",
            "compiled_code": "SELECT\n  o.order_id, o.customer_id, o.amount,\n  p.payment_method, p.amount AS payment_amount\nFROM main.stg_orders o\nLEFT JOIN main.stg_payments p ON o.order_id = p.order_id",
        },
        {
            "unique_id": "model.shop.fct_revenue",
            "status": "success",
            "execution_time": 35.7,
            "message": "OK created sql table model main.fct_revenue",
            "compiled_code": "SELECT\n  date_trunc('month', created_at) AS month,\n  SUM(amount) AS revenue,\n  COUNT(*) AS order_count\nFROM main.stg_orders\nGROUP BY 1",
        },
        {
            "unique_id": "model.shop.dim_customers",
            "status": "success",
            "execution_time": 12.4,
            "message": "OK created sql table model main.dim_customers",
            "compiled_code": "SELECT\n  c.customer_id, c.name, c.email,\n  COUNT(o.order_id) AS order_count,\n  SUM(o.amount) AS lifetime_value\nFROM main.stg_customers c\nLEFT JOIN main.stg_orders o ON c.customer_id = o.customer_id\nGROUP BY 1, 2, 3",
        },
        {
            "unique_id": "model.shop.dim_products",
            "status": "success",
            "execution_time": 5.1,
            "message": "OK created sql table model main.dim_products",
            "compiled_code": "SELECT p.product_id, p.name, p.price, c.name AS category\nFROM main.stg_products p\nLEFT JOIN main.categories c ON p.category_id = c.id",
        },
        {
            "unique_id": "model.shop.stg_returns",
            "status": "error",
            "execution_time": 0.31,
            "message": "Compilation Error: relation 'main.raw_returns' does not exist",
            "compiled_code": "SELECT id, order_id, reason, created_at FROM main.raw_returns",
        },
        {
            "unique_id": "model.shop.int_order_items_pivoted",
            "status": "success",
            "execution_time": 28.9,
            "message": "OK created sql table model main.int_order_items_pivoted",
            "compiled_code": "SELECT order_id, product_id, quantity, unit_price,\n  quantity * unit_price AS line_total\nFROM main.order_items",
        },
        {
            "unique_id": "model.shop.mart_daily_metrics",
            "status": "skipped",
            "execution_time": 0.0,
            "message": "SKIP relation shop.mart_daily_metrics",
            "compiled_code": "SELECT\n  DATE(created_at) AS day,\n  COUNT(*) AS orders,\n  SUM(amount) AS revenue\nFROM main.fct_orders\nGROUP BY 1",
        },
        # Tests — 8 total
        {
            "unique_id": "test.shop.not_null_orders_id",
            "status": "pass",
            "execution_time": 0.12,
            "message": "Pass",
            "compiled_code": "SELECT count(*) AS failures FROM main.stg_orders WHERE order_id IS NULL",
        },
        {
            "unique_id": "test.shop.not_null_customers_id",
            "status": "pass",
            "execution_time": 0.09,
            "message": "Pass",
            "compiled_code": "SELECT count(*) AS failures FROM main.stg_customers WHERE customer_id IS NULL",
        },
        {
            "unique_id": "test.shop.not_null_payments_amount",
            "status": "fail",
            "execution_time": 0.38,
            "message": "Fail 3 (failure threshold: 0)",
            "compiled_code": "SELECT count(*) AS failures FROM main.stg_payments WHERE amount IS NULL",
        },
        {
            "unique_id": "test.shop.accepted_values_orders_status",
            "status": "warn",
            "execution_time": 0.21,
            "message": "Got 2 results, configured to warn if != 0",
            "compiled_code": "SELECT count(*) AS failures\nFROM main.stg_orders\nWHERE status NOT IN ('placed', 'shipped', 'completed', 'returned')",
        },
        {
            "unique_id": "test.shop.unique_orders_id",
            "status": "pass",
            "execution_time": 0.15,
            "message": "Pass",
            "compiled_code": "SELECT order_id, count(*) FROM main.stg_orders GROUP BY 1 HAVING count(*) > 1",
        },
        {
            "unique_id": "test.shop.relationships_orders_customers",
            "status": "fail",
            "execution_time": 0.44,
            "message": "Fail 7 (failure threshold: 0)",
            "compiled_code": "SELECT count(*) FROM main.stg_orders o\nWHERE o.customer_id NOT IN (SELECT customer_id FROM main.stg_customers)",
        },
        {
            "unique_id": "test.shop.not_null_shipments_order_id",
            "status": "pass",
            "execution_time": 0.08,
            "message": "Pass",
            "compiled_code": "SELECT count(*) AS failures FROM main.stg_shipments WHERE order_id IS NULL",
        },
        {
            "unique_id": "test.shop.accepted_values_payments_method",
            "status": "warn",
            "execution_time": 0.19,
            "message": "Got 5 results, configured to warn if != 0",
            "compiled_code": "SELECT count(*) AS failures\nFROM main.stg_payments\nWHERE method NOT IN ('credit_card', 'debit_card', 'paypal', 'bank_transfer')",
        },
        # Snapshots — 3 total
        {
            "unique_id": "snapshot.shop.snap_customers",
            "status": "success",
            "execution_time": 2.1,
            "message": "OK snapshotted",
            "compiled_code": "SELECT id, name, email, updated_at,\n  current_timestamp AS dbt_updated_at\nFROM main.raw_customers",
        },
        {
            "unique_id": "snapshot.shop.snap_orders",
            "status": "success",
            "execution_time": 4.8,
            "message": "OK snapshotted",
            "compiled_code": "SELECT id, customer_id, amount, status, updated_at,\n  current_timestamp AS dbt_updated_at\nFROM main.raw_orders",
        },
        {
            "unique_id": "snapshot.shop.snap_products",
            "status": "success",
            "execution_time": 1.5,
            "message": "OK snapshotted",
            "compiled_code": "SELECT id, name, price, category_id,\n  current_timestamp AS dbt_updated_at\nFROM main.raw_products",
        },
        # Seeds — 2 total
        {
            "unique_id": "seed.shop.raw_countries",
            "status": "success",
            "execution_time": 0.34,
            "message": "OK loaded seed file raw_countries",
            "compiled_code": None,
        },
        {
            "unique_id": "seed.shop.raw_payment_methods",
            "status": "success",
            "execution_time": 0.22,
            "message": "OK loaded seed file raw_payment_methods",
            "compiled_code": None,
        },
        # Sources — 2 total
        {
            "unique_id": "source.shop.raw.orders",
            "status": "pass",
            "execution_time": 0.55,
            "message": "Pass freshness check",
            "compiled_code": "SELECT max(updated_at) FROM main.raw_orders",
        },
        {
            "unique_id": "source.shop.raw.payments",
            "status": "fail",
            "execution_time": 0.48,
            "message": "Fail freshness: last record 72 hours ago (threshold: 24h)",
            "compiled_code": "SELECT max(paid_at) FROM main.raw_payments",
        },
    ]

    run_results = {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/run-results/v5.json",
            "dbt_version": "1.7.0",
            "invocation_id": invocation_id,
        },
        "results": results,
        "elapsed_time": 238.4,
    }
    out = DBT_TARGET_DIR / "run_results.json"
    out.write_text(json.dumps(run_results, indent=2))


# ---------------------------------------------------------------------------
# DuckDB warehouse population
# ---------------------------------------------------------------------------


def _populate_warehouse() -> None:
    """Create and populate all tables in the DuckDB warehouse.

    This replaces the simple 3-table warehouse from seed_db.setup() with a
    richer set of tables matching TABLE_DEFS.
    """
    conn = duckdb.connect(str(DB_PATH))
    now = datetime.now()

    # Drop existing tables/views to rebuild
    for tname, ttype, _ in reversed(TABLE_DEFS):
        kind = "VIEW" if ttype == "VIEW" else "TABLE"
        conn.execute(f"DROP {kind} IF EXISTS {tname}")

    # --- Tables ---

    conn.execute("""
        CREATE TABLE categories (
            id INTEGER, name VARCHAR, parent_id INTEGER
        )
    """)
    categories = [(i, f"Category {i}", None if i <= 5 else (i % 5) + 1) for i in range(1, 21)]
    conn.executemany("INSERT INTO categories VALUES (?, ?, ?)", categories)

    conn.execute("""
        CREATE TABLE suppliers (
            id INTEGER, name VARCHAR, contact_email VARCHAR, country VARCHAR
        )
    """)
    countries = ["US", "UK", "DE", "JP", "CN", "BR", "IN", "CA"]
    suppliers = [
        (i, f"Supplier {i}", f"supplier{i}@vendor.com", countries[i % len(countries)])
        for i in range(1, 26)
    ]
    conn.executemany("INSERT INTO suppliers VALUES (?, ?, ?, ?)", suppliers)

    # products: price stays DOUBLE — drift() changes it to VARCHAR later
    conn.execute("""
        CREATE TABLE products (
            id INTEGER, name VARCHAR, price DOUBLE
        )
    """)
    products = [
        (i, f"Product {i}", round(5.0 + i * 2.5, 2))
        for i in range(1, 201)
    ]
    conn.executemany("INSERT INTO products VALUES (?, ?, ?)", products)

    conn.execute("""
        CREATE TABLE customers (
            id INTEGER, name VARCHAR, email VARCHAR
        )
    """)
    customers = [
        (i, f"Customer {i}", f"customer{i}@example.com") for i in range(1, 301)
    ]
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", customers)

    # orders: NO status column — drift() adds it later
    conn.execute("""
        CREATE TABLE orders (
            id INTEGER, customer_id INTEGER, amount DOUBLE,
            created_at TIMESTAMP, updated_at TIMESTAMP
        )
    """)
    orders = [
        (
            i,
            (i % 300) + 1,
            round(10.0 + (i * 1.37 % 200), 2),
            now - timedelta(hours=i * 0.5),
            now - timedelta(minutes=i * 3),
        )
        for i in range(1, 1501)
    ]
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)

    conn.execute("""
        CREATE TABLE payments (
            id INTEGER, order_id INTEGER, method VARCHAR,
            amount DOUBLE, paid_at TIMESTAMP
        )
    """)
    methods = ["credit_card", "debit_card", "paypal", "bank_transfer", "crypto"]
    payments = [
        (
            i,
            (i % 1500) + 1,
            methods[i % len(methods)],
            round(10.0 + (i * 1.37 % 200), 2),
            now - timedelta(hours=i * 0.6),
        )
        for i in range(1, 1201)
    ]
    conn.executemany("INSERT INTO payments VALUES (?, ?, ?, ?, ?)", payments)

    conn.execute("""
        CREATE TABLE shipments (
            id INTEGER, order_id INTEGER, carrier VARCHAR,
            shipped_at TIMESTAMP, delivered_at TIMESTAMP
        )
    """)
    carriers = ["UPS", "FedEx", "DHL", "USPS"]
    shipments_data = [
        (
            i,
            (i % 1500) + 1,
            carriers[i % len(carriers)],
            now - timedelta(hours=i * 0.7),
            now - timedelta(hours=i * 0.5) if i % 5 != 0 else None,
        )
        for i in range(1, 1001)
    ]
    conn.executemany("INSERT INTO shipments VALUES (?, ?, ?, ?, ?)", shipments_data)

    # returns: NOT created here — drift() creates it later

    conn.execute("""
        CREATE TABLE reviews (
            id INTEGER, customer_id INTEGER, product_id INTEGER,
            rating INTEGER, body VARCHAR, created_at TIMESTAMP
        )
    """)
    bodies = [
        "Great product!",
        "Not what I expected",
        "Excellent quality",
        "Would buy again",
        "Terrible experience",
        "Average, nothing special",
        "Best purchase ever",
    ]
    reviews_data = [
        (
            i,
            (i % 300) + 1,
            (i % 200) + 1,
            (i % 5) + 1,
            bodies[i % len(bodies)],
            now - timedelta(hours=i * 1.5),
        )
        for i in range(1, 501)
    ]
    conn.executemany("INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?)", reviews_data)

    conn.execute("""
        CREATE TABLE inventory (
            id INTEGER, product_id INTEGER, warehouse VARCHAR,
            quantity INTEGER, updated_at TIMESTAMP
        )
    """)
    warehouses = ["US-EAST", "US-WEST", "EU-CENTRAL", "APAC"]
    inventory_data = [
        (
            i,
            (i % 200) + 1,
            warehouses[i % len(warehouses)],
            random.randint(0, 500),
            now - timedelta(hours=i * 2),
        )
        for i in range(1, 451)
    ]
    conn.executemany("INSERT INTO inventory VALUES (?, ?, ?, ?, ?)", inventory_data)

    conn.execute("""
        CREATE TABLE order_items (
            id INTEGER, order_id INTEGER, product_id INTEGER,
            quantity INTEGER, unit_price DOUBLE
        )
    """)
    order_items_data = [
        (
            i,
            (i % 1500) + 1,
            (i % 200) + 1,
            (i % 5) + 1,
            round(5.0 + (i * 1.37 % 100), 2),
        )
        for i in range(1, 3501)
    ]
    conn.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, ?)", order_items_data)

    conn.execute("""
        CREATE TABLE customer_sessions (
            id INTEGER, customer_id INTEGER, started_at TIMESTAMP,
            ended_at TIMESTAMP, page_views INTEGER, device VARCHAR
        )
    """)
    devices = ["desktop", "mobile", "tablet"]
    sessions_data = [
        (
            i,
            (i % 300) + 1,
            now - timedelta(hours=i * 0.3),
            now - timedelta(hours=i * 0.3) + timedelta(minutes=random.randint(1, 120)),
            random.randint(1, 50),
            devices[i % len(devices)],
        )
        for i in range(1, 8001)
    ]
    conn.executemany(
        "INSERT INTO customer_sessions VALUES (?, ?, ?, ?, ?, ?)", sessions_data
    )

    # --- Views ---

    conn.execute("""
        CREATE VIEW order_summary AS
        SELECT customer_id, COUNT(*) AS order_count, SUM(amount) AS total_amount
        FROM orders GROUP BY customer_id
    """)

    conn.execute("""
        CREATE VIEW monthly_revenue AS
        SELECT strftime('%Y-%m', created_at) AS month,
               SUM(amount) AS revenue, COUNT(*) AS order_count
        FROM orders GROUP BY 1
    """)

    conn.execute("""
        CREATE VIEW customer_lifetime_value AS
        SELECT c.id AS customer_id, c.name,
               COALESCE(SUM(o.amount), 0) AS total_spent,
               COUNT(o.id) AS order_count,
               MIN(o.created_at) AS first_order
        FROM customers c
        LEFT JOIN orders o ON c.id = o.customer_id
        GROUP BY c.id, c.name
    """)

    conn.close()


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def seed_rich_dashboard_data(config: OllyConfig) -> None:
    """Generate rich demo data: 30-day history, cost data, expanded dbt results."""
    random.seed(42)  # reproducible

    print("Populating warehouse with 12 tables + 3 views...")
    _populate_warehouse()

    print("Writing expanded dbt run_results.json (26 results)...")
    _write_expanded_dbt_results()

    # Open state DB
    state_dir = get_olly_dir(DEV_DIR)
    state_db = StateDB(state_dir / "state.db")

    now = datetime.now(timezone.utc)
    base_date = now - timedelta(days=30)
    volume_table_names = [t for t, ttype, _ in TABLE_DEFS if ttype == "TABLE"]

    print("Generating 30 days of snapshot history...")
    for day in range(30):
        ts = base_date + timedelta(days=day, hours=random.randint(6, 10), minutes=random.randint(0, 59))
        ts_iso = ts.isoformat()
        day_of_week = ts.weekday()

        # Create snapshot with backdated timestamp
        snapshot_id = state_db._execute(
            f"INSERT INTO {state_db._table('snapshots')} (created_at, connection_name) "
            "VALUES (:created_at, :connection_name)",
            {"created_at": ts_iso, "connection_name": "primary"},
        )
        assert snapshot_id is not None

        # Schema data
        tables = _get_table_schema_at_day(day)
        state_db.store_schema_data(snapshot_id, tables)

        # Volume data
        volumes = []
        for tname in volume_table_names:
            # Skip tables that don't exist yet at this day
            if tname == "reviews" and day < 20:
                continue
            row_count = _compute_row_count(tname, day, day_of_week)
            volumes.append(VolumeRecord(SCHEMA_NAME, tname, row_count))
        state_db.store_volume_data(snapshot_id, volumes)

    print("Generating historical findings (trend data)...")
    for day in range(30):
        ts = base_date + timedelta(days=day, hours=random.randint(10, 14), minutes=random.randint(0, 59))
        ts_iso = ts.isoformat()

        findings = _generate_findings_for_day(day)
        if not findings:
            continue

        for f in findings:
            state_db._execute(
                f"INSERT INTO {state_db._table('findings')} "
                "(created_at, connection_name, check_type, severity, "
                "schema_name, table_name, description, details) "
                "VALUES (:created_at, :connection_name, :check_type, :severity, "
                ":schema_name, :table_name, :description, :details)",
                {
                    "created_at": ts_iso,
                    "connection_name": f["connection_name"],
                    "check_type": f["check_type"],
                    "severity": f["severity"],
                    "schema_name": f["schema_name"],
                    "table_name": f["table_name"],
                    "description": f["description"],
                    "details": "{}",
                },
            )

    print("Generating cost/usage data (10 cost runs)...")
    for run_idx in range(10):
        run_day = 3 + run_idx * 3  # spread over 30 days
        ts = base_date + timedelta(days=run_day, hours=15, minutes=random.randint(0, 59))
        ts_iso = ts.isoformat()

        # Create cost run with backdated timestamp
        run_id = state_db._execute(
            f"INSERT INTO {state_db._table('cost_runs')} (created_at, connection_name) "
            "VALUES (:created_at, :connection_name)",
            {"created_at": ts_iso, "connection_name": "primary"},
        )

        records = _generate_cost_records(volume_table_names)
        for r in records:
            state_db._execute(
                f"INSERT INTO {state_db._table('cost_records')} "
                "(cost_run_id, schema_name, table_name, user_email, "
                "total_bytes_billed, estimated_cost_usd, query_count) "
                "VALUES (:cost_run_id, :schema_name, :table_name, :user_email, "
                ":total_bytes_billed, :estimated_cost_usd, :query_count)",
                {
                    "cost_run_id": run_id,
                    "schema_name": r.schema_name,
                    "table_name": r.table_name,
                    "user_email": r.user_email,
                    "total_bytes_billed": r.total_bytes_billed,
                    "estimated_cost_usd": r.estimated_cost_usd,
                    "query_count": r.query_count,
                },
            )

    state_db.close()
    print("Rich dashboard data seeded successfully!")
